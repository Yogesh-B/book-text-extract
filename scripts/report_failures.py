#!/usr/bin/env python3
"""Failure Reporting CLI for IndicOCR Pipeline.

Scans checkpoint.json files in data/ocr_output/ to inspect:
- Completed page counts vs total expected
- Failed pages with error reasons (e.g. CUDA OOM)
- Missing output files
Outputs a formatted markdown table to console and optionally writes a JSON summary.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import BOOKS_DIR, OCR_OUTPUT_DIR
from src.utils.logger import get_logger
from src.utils.pages import format_page_list
from src.utils.slug import slugify_filename

logger = get_logger("report_failures")


def inspect_book_checkpoint(
    book_slug: str,
    ocr_dir: Path,
    pdf_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Inspect checkpoint and output directory for a specific book slug."""
    book_dir = ocr_dir / book_slug
    checkpoint_file = book_dir / "checkpoint.json"
    raw_json_dir = book_dir / "raw" / "json"
    raw_md_dir = book_dir / "raw" / "markdown"

    info: Dict[str, Any] = {
        "book_slug": book_slug,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "checkpoint_exists": checkpoint_file.exists(),
        "total_pages": 0,
        "completed_count": 0,
        "failed_count": 0,
        "missing_count": 0,
        "failed_pages": {},     # str(pnum) -> error_msg
        "missing_pages": [],    # List[int]
        "status": "not_started",
    }

    if not checkpoint_file.exists():
        return info

    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        total_pages = data.get("total_pages", 0)
        completed_pages = set(data.get("completed_pages", []))
        failed_pages = data.get("failed_pages", {})

        # Verify disk output files for each marked completed page
        verified_completed: List[int] = []
        missing_output_pages: List[int] = []

        for p in sorted(list(completed_pages)):
            json_f = raw_json_dir / f"page_{p:04d}.json"
            md_f = raw_md_dir / f"page_{p:04d}.md"
            if json_f.exists() and json_f.stat().st_size > 0 and md_f.exists() and md_f.stat().st_size > 0:
                verified_completed.append(p)
            else:
                missing_output_pages.append(p)

        # Missing pages: pages between 1 and total_pages that are neither completed nor in failed_pages
        all_expected = set(range(1, total_pages + 1)) if total_pages > 0 else set()
        failed_nums = set()
        for k in failed_pages.keys():
            try:
                failed_nums.add(int(k))
            except ValueError:
                pass

        missing_pages = sorted(list(all_expected - set(verified_completed) - failed_nums))
        missing_pages.extend(missing_output_pages)
        missing_pages = sorted(list(set(missing_pages)))

        info.update({
            "total_pages": total_pages,
            "completed_count": len(verified_completed),
            "failed_count": len(failed_pages),
            "missing_count": len(missing_pages),
            "failed_pages": failed_pages,
            "missing_pages": missing_pages,
            "status": data.get("status", "in_progress"),
        })

    except Exception as e:
        logger.error(f"Error reading checkpoint for {book_slug}: {e}")
        info["status"] = "error"

    return info


def generate_report(
    book_slugs: Optional[List[str]] = None,
    part_file: Optional[Path] = None,
    output_json: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scan and generate a report across specified books or all books in data/ocr_output/."""
    books_to_check: List[tuple[str, Optional[Path]]] = []

    if part_file:
        if not part_file.exists():
            logger.error(f"Part file not found: {part_file}")
            sys.exit(1)
        with open(part_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pdf_path = BOOKS_DIR / line
                slug = slugify_filename(pdf_path)
                books_to_check.append((slug, pdf_path))
    elif book_slugs:
        for slug in book_slugs:
            books_to_check.append((slug, None))
    else:
        # Scan all directories in OCR_OUTPUT_DIR
        if OCR_OUTPUT_DIR.exists():
            for d in sorted(OCR_OUTPUT_DIR.iterdir()):
                if d.is_dir() and (d / "checkpoint.json").exists():
                    books_to_check.append((d.name, None))

    results = []
    for slug, pdf_p in books_to_check:
        info = inspect_book_checkpoint(slug, OCR_OUTPUT_DIR, pdf_p)
        results.append(info)

    # Print markdown table report
    print("\n" + "=" * 80)
    print("                    INDICOCR EXECUTION & FAILURE REPORT                    ")
    print("=" * 80)

    total_books = len(results)
    books_with_failures = 0
    total_failed_pages = 0

    header = f"{'Book Slug':<35} | {'Total':<6} | {'Done':<6} | {'Fail':<6} | {'Miss':<6} | {'Status':<12}"
    print(header)
    print("-" * len(header))

    for r in results:
        is_issue = r["failed_count"] > 0 or r["missing_count"] > 0
        if is_issue:
            books_with_failures += 1
            total_failed_pages += r["failed_count"] + r["missing_count"]

        status_disp = r["status"]
        print(
            f"{r['book_slug'][:35]:<35} | "
            f"{r['total_pages']:<6} | "
            f"{r['completed_count']:<6} | "
            f"{r['failed_count']:<6} | "
            f"{r['missing_count']:<6} | "
            f"{status_disp:<12}"
        )

    print("=" * 80)
    print(f"Summary: {total_books} book(s) audited. {books_with_failures} book(s) have incomplete/failed pages ({total_failed_pages} total pages).")

    # Detailed breakdown of failures
    failed_details = [r for r in results if r["failed_count"] > 0 or r["missing_count"] > 0]
    if failed_details:
        print("\n--- DETAILED FAILURE & MISSING BREAKDOWN ---")
        for r in failed_details:
            print(f"\n* Book: {r['book_slug']}")
            if r["failed_pages"]:
                print("  Failed Pages:")
                for p, err in sorted(r["failed_pages"].items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                    # Shorten error msg for readability
                    short_err = err.split("\n")[0][:80]
                    print(f"    - Page {int(p):04d}: {short_err}")
                print(f"  Summary Range of Failed Pages: {format_page_list([int(p) for p in r['failed_pages'].keys() if p.isdigit()])}")
            if r["missing_pages"]:
                print(f"  Missing Pages (not in checkpoint/output): {format_page_list(r['missing_pages'])}")

    print("=" * 80 + "\n")

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Detailed failure report saved to {output_json}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Report failed and incomplete pages across OCR outputs.")
    parser.add_argument("--book", "-b", type=str, help="Specific book slug to inspect")
    parser.add_argument("--part", "-p", type=str, help="Path to part file (e.g. temp/parts/part_1.txt)")
    parser.add_argument("--output", "-o", type=str, default="data/ocr_output/failure_report.json", help="Path to write JSON report")
    args = parser.parse_args()

    slugs = [args.book] if args.book else None
    part_path = Path(args.part) if args.part else None
    out_path = Path(args.output) if args.output else None

    generate_report(book_slugs=slugs, part_file=part_path, output_json=out_path)


if __name__ == "__main__":
    main()
