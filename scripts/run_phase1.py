#!/usr/bin/env python3
"""Phase 1: PDF to High-Resolution Image Conversion CLI.

Converts Gujarati book PDFs to 300 DPI lossless PNG images for OCR processing.
Outputs images to data/images/<book_slug>/ along with manifest.json.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import BOOKS_DIR, DEFAULT_DPI, DEFAULT_WORKERS
from src.phase1_pdf_to_images.extractor import PDFImageExtractor
from src.utils.logger import get_logger
from src.utils.pages import parse_page_selection

logger = get_logger("run_phase1")


def parse_page_range(range_str: str) -> tuple[int, int]:
    """Parse page range like '1-20' or '10'."""
    pages = parse_page_selection(range_str)
    return min(pages), max(pages)


def main():
    parser = argparse.ArgumentParser(
        description="Extract 300 DPI images from Gujarati PDFs for IndicOCR pipeline."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="Path to a single input PDF file (e.g. books/Nari Ratno (SGVP).pdf)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all PDF files found in the books/ directory",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Target rendering DPI (default: {DEFAULT_DPI})",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of parallel worker processes (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Custom destination directory (default: data/images/<book_slug>/)",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help="Explicit book slug to override auto-detected slug",
    )
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Page range to extract, e.g. '1-20' or '5'",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to extract (useful for smoke tests)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite of existing page images",
    )

    args = parser.parse_args()

    if not args.input and not args.all:
        parser.error("Either --input <path> or --all must be specified.")

    # Collect PDF files to process
    pdf_files: list[Path] = []
    if args.all:
        if not BOOKS_DIR.exists():
            logger.error(f"Books directory not found: {BOOKS_DIR}")
            sys.exit(1)
        pdf_files = sorted(BOOKS_DIR.glob("*.pdf"))
        if not pdf_files:
            logger.error(f"No PDF files found in {BOOKS_DIR}")
            sys.exit(1)
        logger.info(f"Found {len(pdf_files)} PDF(s) to process in {BOOKS_DIR}")
    else:
        target = Path(args.input)
        if not target.exists():
            logger.error(f"PDF file not found: {target}")
            sys.exit(1)
        pdf_files = [target]

    target_page_numbers = None
    if args.pages:
        target_page_numbers = parse_page_selection(args.pages)

    total_extracted = 0
    total_skipped = 0
    total_failed = 0

    for idx, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"[{idx}/{len(pdf_files)}] Processing: {pdf_path.name}")
        try:
            extractor = PDFImageExtractor(
                pdf_path=pdf_path,
                output_dir=args.output_dir,
                dpi=args.dpi,
                workers=args.workers,
                book_slug=args.slug if len(pdf_files) == 1 else None,
            )
            result = extractor.extract(
                page_numbers=target_page_numbers,
                max_pages=args.max_pages,
                force=args.force,
            )
            total_extracted += result.extracted_count
            total_skipped += result.skipped_count
            total_failed += result.failed_count
            logger.info(f"Finished {pdf_path.name}: {result.extracted_count} rendered, manifest at {result.manifest_path}")
        except Exception as e:
            logger.exception(f"Failed processing {pdf_path.name}: {e}")
            total_failed += 1

    logger.info(
        f"All done! Summary: {total_extracted} pages rendered, "
        f"{total_skipped} skipped, {total_failed} errors."
    )


if __name__ == "__main__":
    main()
