#!/usr/bin/env python3
"""Targeted Failed Pages Retry CLI.

Extracts ONLY failed/incomplete pages as images for specified book(s),
and re-runs IndicOCR processing with custom safer options (e.g. smaller batch size),
then immediately cleans up the temporary images.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import BOOKS_DIR, IMAGES_DIR, OCR_OUTPUT_DIR
from src.phase1_pdf_to_images.extractor import PDFImageExtractor
from src.phase2_indic_ocr.parser import IndicOCRParser
from src.utils.logger import get_logger
from src.utils.pages import format_page_list, parse_page_selection
from src.utils.slug import slugify_filename
from scripts.report_failures import inspect_book_checkpoint
from scripts.run_phase2 import process_book

logger = get_logger("retry_failed")


def find_pdf_for_slug(book_slug: str) -> Optional[Path]:
    """Find the PDF file corresponding to a given slug in BOOKS_DIR."""
    if not BOOKS_DIR.exists():
        return None
    for pdf_file in BOOKS_DIR.glob("*.pdf"):
        if slugify_filename(pdf_file) == book_slug:
            return pdf_file
    return None


def retry_book_pages(
    book_slug: str,
    pdf_path: Optional[Path] = None,
    specific_pages: Optional[List[int]] = None,
    ocr_parser: Optional[IndicOCRParser] = None,
    crop_batch_size: int = 8,
    device: Optional[str] = None,
    cleanup_images: bool = True,
    workers: int = 4,
) -> dict:
    """Extract only targeted pages from PDF and run Phase 2 OCR."""
    if not pdf_path:
        pdf_path = find_pdf_for_slug(book_slug)

    if not pdf_path or not pdf_path.exists():
        logger.error(f"Cannot find source PDF for slug: '{book_slug}'")
        return {"processed": 0, "failed": 1}

    # Inspect current checkpoint to know which pages need retry if not explicitly provided
    if specific_pages is None:
        info = inspect_book_checkpoint(book_slug, OCR_OUTPUT_DIR, pdf_path)
        failed_nums = [int(p) for p in info["failed_pages"].keys() if p.isdigit()]
        missing_nums = info["missing_pages"]
        pages_to_retry = sorted(list(set(failed_nums + missing_nums)))
    else:
        pages_to_retry = sorted(list(set(specific_pages)))

    if not pages_to_retry:
        logger.info(f"Book '{book_slug}': No failed or requested pages to retry. All good!")
        return {"processed": 0, "failed": 0}

    logger.info("=" * 70)
    logger.info(f"Retrying {len(pages_to_retry)} page(s) for '{book_slug}'")
    logger.info(f"Pages: {format_page_list(pages_to_retry)}")
    logger.info(f"Using crop batch size: {crop_batch_size}")
    logger.info("=" * 70)

    # 1. Extract ONLY those specific pages to data/images/<book_slug>/
    images_dir = IMAGES_DIR / book_slug
    images_dir.mkdir(parents=True, exist_ok=True)

    extractor = PDFImageExtractor(
        pdf_path=pdf_path,
        output_dir=images_dir,
        dpi=300,
        workers=workers,
        book_slug=book_slug,
    )
    extract_res = extractor.extract(
        page_numbers=pages_to_retry,
        force=True,  # Force re-rendering fresh images for failed pages
    )
    logger.info(f"Rendered {extract_res.extracted_count} page images for retry.")

    # 2. Run Phase 2 OCR on these pages
    local_parser = False
    if ocr_parser is None:
        local_parser = True
        logger.info(f"Initializing IndicOCR engine (batch size: {crop_batch_size})...")
        ocr_parser = IndicOCRParser(
            device=device,
            crop_batch_size=crop_batch_size,
        )

    try:
        stats = process_book(
            images_dir=images_dir,
            book_slug=book_slug,
            parser=ocr_parser,
            target_page_numbers=pages_to_retry,
            force=True,  # Overwrite previous failed state
        )
    finally:
        # 3. Clean up intermediate images
        if cleanup_images:
            logger.info(f"Cleaning up retry images: {images_dir}")
            shutil.rmtree(images_dir, ignore_errors=True)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Retry failed pages with targeted image extraction and smaller batch size.")
    parser.add_argument("--book", "-b", type=str, help="Book slug or subdirectory name")
    parser.add_argument("--pdf", type=str, help="Direct path to PDF (if book slug not auto-located)")
    parser.add_argument("--part", "-p", type=str, help="Path to part file (e.g. temp/parts/part_1.txt) to retry all failed books in it")
    parser.add_argument("--all", action="store_true", help="Scan all books in data/ocr_output/ and retry any failures")
    parser.add_argument("--pages", type=str, default=None, help="Explicit pages to retry, e.g. '5,12,42-45'")
    parser.add_argument("--crop-batch-size", type=int, default=8, help="Safer crop batch size for retry (default: 8)")
    parser.add_argument("--device", type=str, default=None, choices=["cuda", "cpu"], help="Explicit compute device")
    parser.add_argument("--keep-images", action="store_true", help="Keep extracted page images after processing")
    parser.add_argument("--workers", type=int, default=4, help="Phase 1 image rendering workers")

    args = parser.parse_args()

    explicit_pages = parse_page_selection(args.pages) if args.pages else None

    books_to_retry: List[tuple[str, Optional[Path]]] = []

    if args.book:
        pdf_p = Path(args.pdf) if args.pdf else None
        books_to_retry.append((args.book, pdf_p))
    elif args.part:
        part_path = Path(args.part)
        if not part_path.exists():
            logger.error(f"Part file not found: {part_path}")
            sys.exit(1)
        with open(part_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pdf_p = BOOKS_DIR / line
                slug = slugify_filename(pdf_p)
                books_to_retry.append((slug, pdf_p))
    elif args.all:
        if OCR_OUTPUT_DIR.exists():
            for d in sorted(OCR_OUTPUT_DIR.iterdir()):
                if d.is_dir() and (d / "checkpoint.json").exists():
                    books_to_retry.append((d.name, None))
    else:
        parser.error("Specify --book <slug>, --part <file>, or --all")

    if not books_to_retry:
        logger.info("No books found to inspect for retry.")
        return

    # Check which books actually have pages needing retry
    actionable_books = []
    for slug, pdf_p in books_to_retry:
        if explicit_pages:
            actionable_books.append((slug, pdf_p, explicit_pages))
        else:
            info = inspect_book_checkpoint(slug, OCR_OUTPUT_DIR, pdf_p)
            pages = sorted(list(set([int(p) for p in info["failed_pages"].keys() if p.isdigit()] + info["missing_pages"])))
            if pages:
                actionable_books.append((slug, pdf_p, pages))

    if not actionable_books:
        logger.info("Great news! No failed or missing pages found across specified books.")
        return

    logger.info(f"Found {len(actionable_books)} book(s) needing retry. Initializing IndicOCR engine...")
    shared_parser = IndicOCRParser(
        device=args.device,
        crop_batch_size=args.crop_batch_size,
    )

    total_fixed = 0
    total_still_failed = 0

    for idx, (slug, pdf_p, pages) in enumerate(actionable_books, 1):
        logger.info(f"[{idx}/{len(actionable_books)}] Retrying book: {slug}")
        stats = retry_book_pages(
            book_slug=slug,
            pdf_path=pdf_p,
            specific_pages=pages,
            ocr_parser=shared_parser,
            crop_batch_size=args.crop_batch_size,
            device=args.device,
            cleanup_images=not args.keep_images,
            workers=args.workers,
        )
        total_fixed += stats.get("processed", 0)
        total_still_failed += stats.get("failed", 0)

    logger.info("=" * 70)
    logger.info(f"Retry complete: {total_fixed} page(s) successfully processed, {total_still_failed} failed.")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
