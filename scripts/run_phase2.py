#!/usr/bin/env python3
"""Phase 2: IndicOCR Batch Pipeline CLI.

Transcribes high-resolution page images from Phase 1 into immutable raw JSON
and reading-ordered Markdown files using bodhan-ai/indic-ocr.
Tracks progress via checkpoint.json for crash recovery and resumption.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Enable expandable segments by default to avoid PyTorch CUDA memory fragmentation on <=4GB GPUs
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tqdm import tqdm

from src.config import (
    IMAGES_DIR,
    OCR_OUTPUT_DIR,
    get_ocr_checkpoint_file,
    get_ocr_raw_json_dir,
    get_ocr_raw_md_dir,
)
from src.phase2_indic_ocr.checkpoint_manager import CheckpointManager
from src.phase2_indic_ocr.parser import IndicOCRParser
from src.utils.logger import get_logger

logger = get_logger("run_phase2")


def parse_page_range(range_str: str) -> Tuple[int, int]:
    """Parse a page range string such as '1-20' or '15'."""
    if "-" in range_str:
        parts = range_str.split("-")
        return int(parts[0].strip()), int(parts[1].strip())
    page = int(range_str.strip())
    return page, page


def extract_page_num_from_path(p: Path) -> Optional[int]:
    """Extract page number from filename like page_0042.png."""
    match = re.search(r"page_(\d+)", p.stem)
    if match:
        return int(match.group(1))
    return None


def discover_book_pages(images_dir: Path) -> List[Tuple[int, Path]]:
    """Find all page images in the given directory sorted by page number."""
    pages = []
    for img_path in images_dir.glob("page_*.png"):
        pnum = extract_page_num_from_path(img_path)
        if pnum is not None:
            pages.append((pnum, img_path))
    pages.sort(key=lambda x: x[0])
    return pages


def process_book(
    images_dir: Path,
    book_slug: str,
    parser: IndicOCRParser,
    target_page_range: Optional[Tuple[int, int]] = None,
    max_pages: Optional[int] = None,
    reorder: bool = True,
    y_tolerance: float = 20.0,
    force: bool = False,
    output_root: Optional[Path] = None,
) -> dict:
    """Process a single book directory of page images."""
    logger.info(f"Starting OCR batch for book: '{book_slug}' from {images_dir}")

    all_pages = discover_book_pages(images_dir)
    if not all_pages:
        logger.error(f"No page images found in {images_dir}")
        return {"total": 0, "processed": 0, "skipped": 0, "failed": 0}

    total_pages_found = len(all_pages)
    logger.info(f"Discovered {total_pages_found} page image(s) for '{book_slug}'.")

    # Apply page range filter if requested
    if target_page_range:
        p_start, p_end = target_page_range
        all_pages = [p for p in all_pages if p_start <= p[0] <= p_end]

    if max_pages is not None:
        all_pages = all_pages[:max_pages]

    # Setup directories
    if output_root:
        base_dir = output_root / book_slug
        raw_json_dir = base_dir / "raw" / "json"
        raw_md_dir = base_dir / "raw" / "markdown"
        checkpoint_path = base_dir / "checkpoint.json"
    else:
        raw_json_dir = get_ocr_raw_json_dir(book_slug)
        raw_md_dir = get_ocr_raw_md_dir(book_slug)
        checkpoint_path = get_ocr_checkpoint_file(book_slug)

    raw_json_dir.mkdir(parents=True, exist_ok=True)
    raw_md_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Checkpoint Manager
    checkpoint = CheckpointManager(
        checkpoint_path=checkpoint_path,
        book_slug=book_slug,
        total_pages=total_pages_found,
    )

    # Identify pages that need processing
    pending_pages = []
    skipped_count = 0
    for pnum, img_path in all_pages:
        if not force and checkpoint.is_completed(pnum, raw_json_dir, raw_md_dir):
            skipped_count += 1
        else:
            pending_pages.append((pnum, img_path))

    logger.info(
        f"Book: '{book_slug}' | Total Target Pages: {len(all_pages)} | "
        f"Already Completed: {skipped_count} | To Process: {len(pending_pages)}"
    )

    if not pending_pages:
        logger.info(f"All target pages for '{book_slug}' are already completed. Nothing to do!")
        return {
            "total": len(all_pages),
            "processed": 0,
            "skipped": skipped_count,
            "failed": 0,
        }

    processed_count = 0
    failed_count = 0

    with tqdm(total=len(pending_pages), desc=f"OCR {book_slug}", unit="page") as pbar:
        for pnum, img_path in pending_pages:
            try:
                t0 = time.time()
                result = parser.parse_page(
                    image_path=img_path,
                    reorder=reorder,
                    y_tolerance=y_tolerance,
                )
                duration = time.time() - t0

                # Save raw outputs
                json_path, md_path = parser.save_page_output(
                    result=result,
                    page_num=pnum,
                    json_dir=raw_json_dir,
                    md_dir=raw_md_dir,
                )

                block_count = len(result.get("blocks", []))
                checkpoint.record_success(
                    page_num=pnum,
                    duration_sec=duration,
                    block_count=block_count,
                )
                checkpoint.save()

                processed_count += 1
                logger.debug(
                    f"Page {pnum:04d} done in {duration:.2f}s ({block_count} blocks) -> {md_path.name}"
                )

            except Exception as e:
                failed_count += 1
                logger.exception(f"Failed OCR for {book_slug} page {pnum}: {e}")
                checkpoint.record_failure(page_num=pnum, error_msg=str(e))
                checkpoint.save()
                if "out of memory" in str(e).lower():
                    logger.warning(
                        f"VRAM Out-of-Memory encountered on page {pnum}. "
                        "If this page fails repeatedly, consider running with --device cpu."
                    )

            finally:
                parser.cleanup_memory()
                pbar.update(1)

    checkpoint.save(is_final=True)
    logger.info(
        f"Batch finished for '{book_slug}': {processed_count} processed, "
        f"{skipped_count} skipped, {failed_count} errors. "
        f"Checkpoint saved to {checkpoint_path}"
    )

    return {
        "total": len(all_pages),
        "processed": processed_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Phase 2 batch IndicOCR pipeline on extracted page images."
    )
    parser.add_argument(
        "--book", "-b",
        type=str,
        default=None,
        help="Book slug or subdirectory name in data/images/ (e.g. 'Aadarsh_bhaktgatha')",
    )
    parser.add_argument(
        "--images-dir", "-i",
        type=str,
        default=None,
        help="Direct path to page images directory (overrides --book)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all books found in data/images/",
    )
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Page range to process, e.g. '1-20' or '50'",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit number of pages to process (useful for smoke tests)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Custom output directory (default: data/ocr_output/<book_slug>/)",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Custom path to indic-ocr model weights",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cuda", "cpu"],
        help="Explicit compute device ('cuda' or 'cpu')",
    )
    parser.add_argument(
        "--no-reorder",
        action="store_true",
        help="Disable column clustering & top-to-bottom reordering",
    )
    parser.add_argument(
        "--y-tolerance",
        type=float,
        default=20.0,
        help="Vertical tolerance in pixels for ordering same-line elements (default: 20.0)",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Optimize recognizer model using torch.compile(dynamic=True) for ~18%% faster inference",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite of existing OCR outputs and re-run completed pages",
    )
    parser.add_argument(
        "--crop-batch-size",
        type=int,
        default=None,
        help="Batch size of text-box image crops during recognizer inference (default: auto 2 on <=4.5GB GPUs, 8 on larger GPUs). Set to 1 or 2 to prevent CUDA OOM on dense pages.",
    )

    args = parser.parse_args()

    if not args.book and not args.images_dir and not args.all:
        parser.error("Please specify --book <slug>, --images-dir <path>, or --all")

    # Discover books to process
    books_to_process: List[Tuple[str, Path]] = []
    if args.images_dir:
        dir_path = Path(args.images_dir).resolve()
        if not dir_path.exists():
            logger.error(f"Images directory not found: {dir_path}")
            sys.exit(1)
        books_to_process.append((dir_path.name, dir_path))
    elif args.book:
        target_dir = IMAGES_DIR / args.book
        if not target_dir.exists():
            logger.error(f"Book image directory not found: {target_dir}")
            sys.exit(1)
        books_to_process.append((args.book, target_dir))
    elif args.all:
        if not IMAGES_DIR.exists():
            logger.error(f"Images directory not found: {IMAGES_DIR}")
            sys.exit(1)
        for sub in sorted(IMAGES_DIR.iterdir()):
            if sub.is_dir() and any(sub.glob("page_*.png")):
                books_to_process.append((sub.name, sub))
        if not books_to_process:
            logger.error(f"No book image directories found in {IMAGES_DIR}")
            sys.exit(1)
        logger.info(f"Found {len(books_to_process)} book(s) to process.")

    target_page_range = parse_page_range(args.pages) if args.pages else None
    output_root = Path(args.output_dir).resolve() if args.output_dir else None

    # Lazy-load parser once for all books
    logger.info("Initializing IndicOCR engine...")
    ocr_parser = IndicOCRParser(
        model_path=args.model_path,
        device=args.device,
        compile_model=args.compile,
        crop_batch_size=args.crop_batch_size,
    )

    grand_total_processed = 0
    grand_total_skipped = 0
    grand_total_failed = 0

    for idx, (slug, img_dir) in enumerate(books_to_process, 1):
        logger.info(f"[{idx}/{len(books_to_process)}] Processing book: {slug}")
        stats = process_book(
            images_dir=img_dir,
            book_slug=slug,
            parser=ocr_parser,
            target_page_range=target_page_range,
            max_pages=args.max_pages,
            reorder=not args.no_reorder,
            y_tolerance=args.y_tolerance,
            force=args.force,
            output_root=output_root,
        )
        grand_total_processed += stats["processed"]
        grand_total_skipped += stats["skipped"]
        grand_total_failed += stats["failed"]

    logger.info("=" * 60)
    logger.info(
        f"All done! Summary across {len(books_to_process)} book(s): "
        f"{grand_total_processed} pages transcribed, "
        f"{grand_total_skipped} skipped, {grand_total_failed} errors."
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
