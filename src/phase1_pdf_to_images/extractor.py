import hashlib
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf
from pydantic import BaseModel
from tqdm import tqdm

from src.config import DEFAULT_DPI, IMAGES_DIR, get_book_slug
from src.utils.logger import get_logger

logger = get_logger("phase1_extractor")


class PageMetadata(BaseModel):
    page_num: int
    file_name: str
    width: int
    height: int


class ExtractionManifest(BaseModel):
    book_name: str
    book_slug: str
    pdf_path: str
    pdf_sha256: str
    total_pdf_pages: int
    extracted_pages_count: int
    dpi: int
    image_format: str
    extracted_at: str
    pages: List[PageMetadata]


class ExtractionResult(BaseModel):
    book_slug: str
    output_dir: str
    total_pages: int
    extracted_count: int
    skipped_count: int
    failed_count: int
    manifest_path: str


def compute_sha256(file_path: Path, block_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _render_chunk_worker(args: tuple) -> List[Dict[str, Any]]:
    """Worker function to render a chunk of pages using PyMuPDF."""
    pdf_path_str, page_indices, out_dir_str, dpi, force = args
    out_dir = Path(out_dir_str)
    results = []

    doc = None
    try:
        doc = pymupdf.open(pdf_path_str)
        for page_idx in page_indices:
            page_num = page_idx + 1
            filename = f"page_{page_num:04d}.png"
            out_file = out_dir / filename

            # Skip if already exists and valid
            if out_file.exists() and out_file.stat().st_size > 0 and not force:
                page = doc[page_idx]
                rect = page.rect
                zoom = dpi / 72.0
                results.append({
                    "page_num": page_num,
                    "file_name": filename,
                    "width": int(round(rect.width * zoom)),
                    "height": int(round(rect.height * zoom)),
                    "skipped": True,
                    "error": None,
                })
                continue

            try:
                page = doc[page_idx]
                # Render at target DPI (alpha=False ensures RGB, smaller footprint)
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                pix.save(str(out_file))
                results.append({
                    "page_num": page_num,
                    "file_name": filename,
                    "width": pix.width,
                    "height": pix.height,
                    "skipped": False,
                    "error": None,
                })
            except Exception as e:
                results.append({
                    "page_num": page_num,
                    "file_name": filename,
                    "width": 0,
                    "height": 0,
                    "skipped": False,
                    "error": str(e),
                })
    finally:
        if doc is not None:
            doc.close()

    return results


class PDFImageExtractor:
    """Extracts high-resolution images from PDF documents using PyMuPDF."""

    def __init__(
        self,
        pdf_path: str | Path,
        output_dir: Optional[str | Path] = None,
        dpi: int = DEFAULT_DPI,
        workers: Optional[int] = None,
        book_slug: Optional[str] = None,
    ):
        self.pdf_path = Path(pdf_path).resolve()
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        self.dpi = dpi
        self.book_slug = book_slug or get_book_slug(self.pdf_path)

        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = (IMAGES_DIR / self.book_slug).resolve()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Worker count: default to min(cpu_count, 8)
        max_cpus = os.cpu_count() or 4
        self.workers = workers or min(max_cpus, 8)

    def extract(
        self,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        max_pages: Optional[int] = None,
        force: bool = False,
        chunk_size: int = 10,
    ) -> ExtractionResult:
        """Extract pages to 300 DPI PNG images.

        Args:
            start_page: 1-indexed start page (inclusive).
            end_page: 1-indexed end page (inclusive).
            max_pages: Limit total pages to extract.
            force: If True, re-render already existing page images.
            chunk_size: Number of pages processed per worker batch.

        Returns:
            ExtractionResult with statistics and manifest path.
        """
        logger.info(f"Opening PDF: {self.pdf_path.name}")
        doc = pymupdf.open(str(self.pdf_path))
        total_pdf_pages = len(doc)
        doc.close()

        # Determine target page indices (0-indexed)
        p_start = max(1, start_page or 1)
        p_end = min(total_pdf_pages, end_page or total_pdf_pages)
        if max_pages is not None:
            p_end = min(p_end, p_start + max_pages - 1)

        target_indices = list(range(p_start - 1, p_end))
        total_to_process = len(target_indices)

        logger.info(
            f"Book: '{self.book_slug}' | Total PDF Pages: {total_pdf_pages} | "
            f"Extracting Pages {p_start} to {p_end} ({total_to_process} pages) at {self.dpi} DPI "
            f"using {self.workers} workers"
        )

        # Divide into chunks for workers
        chunks = []
        for i in range(0, total_to_process, chunk_size):
            chunks.append(target_indices[i : i + chunk_size])

        tasks = [
            (str(self.pdf_path), chunk, str(self.output_dir), self.dpi, force)
            for chunk in chunks
        ]

        extracted_count = 0
        skipped_count = 0
        failed_count = 0
        page_records: List[Dict[str, Any]] = []

        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(_render_chunk_worker, task): task for task in tasks}
            with tqdm(total=total_to_process, desc=f"Extracting {self.book_slug}", unit="page") as pbar:
                for future in as_completed(futures):
                    chunk_results = future.result()
                    for res in chunk_results:
                        page_records.append(res)
                        if res["error"]:
                            failed_count += 1
                            logger.error(f"Error extracting page {res['page_num']}: {res['error']}")
                        elif res["skipped"]:
                            skipped_count += 1
                        else:
                            extracted_count += 1
                    pbar.update(len(chunk_results))

        # Sort results by page number
        page_records.sort(key=lambda x: x["page_num"])

        # Load existing manifest if present to merge records (for partial runs)
        manifest_file = self.output_dir / "manifest.json"
        existing_pages: Dict[int, PageMetadata] = {}
        if manifest_file.exists() and not force:
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for p in data.get("pages", []):
                        existing_pages[p["page_num"]] = PageMetadata(**p)
            except Exception as e:
                logger.warning(f"Could not load existing manifest.json: {e}")

        for rec in page_records:
            if not rec["error"]:
                existing_pages[rec["page_num"]] = PageMetadata(
                    page_num=rec["page_num"],
                    file_name=rec["file_name"],
                    width=rec["width"],
                    height=rec["height"],
                )

        sorted_pages = [existing_pages[k] for k in sorted(existing_pages.keys())]

        pdf_sha256 = compute_sha256(self.pdf_path)

        manifest = ExtractionManifest(
            book_name=self.pdf_path.stem,
            book_slug=self.book_slug,
            pdf_path=str(self.pdf_path),
            pdf_sha256=pdf_sha256,
            total_pdf_pages=total_pdf_pages,
            extracted_pages_count=len(sorted_pages),
            dpi=self.dpi,
            image_format="png",
            extracted_at=datetime.now(timezone.utc).isoformat(),
            pages=sorted_pages,
        )

        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        logger.info(
            f"Extraction complete for '{self.book_slug}': "
            f"{extracted_count} rendered, {skipped_count} skipped, {failed_count} failed. "
            f"Manifest saved to {manifest_file}"
        )

        return ExtractionResult(
            book_slug=self.book_slug,
            output_dir=str(self.output_dir),
            total_pages=total_pdf_pages,
            extracted_count=extracted_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            manifest_path=str(manifest_file),
        )
