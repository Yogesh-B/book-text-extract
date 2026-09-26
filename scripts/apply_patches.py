#!/usr/bin/env python3
"""
scripts/apply_patches.py — Phase 3.5: Review and apply generated patches.

Modes:
  --interactive  (default) Prompt [y/n/a/q] per change hunk
  --batch        Auto-accept all or filtered change types
  --dry-run      Preview changes without writing any files

Usage:
  # Interactive (default)
  python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha

  # Batch: accept only safe punctuation/space fixes
  python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha \\
      --batch --accept-types punctuation_clean space_fix

  # Batch: accept all changes
  python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --batch --all

  # Dry-run preview
  python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --dry-run

  # Process a specific page range
  python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --pages 1-5
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from src.config import OCR_OUTPUT_DIR, get_ocr_raw_md_dir
from src.phase3_text_verification.patch_applier import apply_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("apply_patches")


VALID_CHANGE_TYPES = {
    "punctuation_clean",
    "space_fix",
    "conjunct_fix",
    "spelling_fix",
    "insert",
    "remove",
}


def _parse_page_range(spec: str | None, max_page: int) -> list[int]:
    if spec is None:
        return list(range(1, max_page + 1))
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(spec)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Phase 3.5: Apply LLM-generated patches into verified/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--book-slug", required=True,
        help="Book slug, e.g. 'Aadarsh_bhaktgatha'",
    )
    p.add_argument(
        "--pages", default=None,
        help="Page range to process, e.g. '1-10' or '5'. Omit for all.",
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--interactive", action="store_true", default=True,
        help="(default) Prompt per change hunk",
    )
    mode.add_argument(
        "--batch", action="store_true",
        help="Auto-accept without prompting",
    )
    mode.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes, write nothing",
    )

    p.add_argument(
        "--accept-types", nargs="+", metavar="TYPE",
        help=(
            "With --batch: only auto-accept these change types. "
            f"Valid: {', '.join(sorted(VALID_CHANGE_TYPES))}"
        ),
    )
    p.add_argument(
        "--all", dest="accept_all", action="store_true",
        help="With --batch: accept all change types (same as no --accept-types)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    book_slug: str = args.book_slug
    raw_md_dir = get_ocr_raw_md_dir(book_slug)
    patches_dir = OCR_OUTPUT_DIR / book_slug / "patches"
    verified_md_dir = OCR_OUTPUT_DIR / book_slug / "verified" / "markdown"

    if not raw_md_dir.exists():
        logger.error("Raw markdown dir not found: %s", raw_md_dir)
        return 1
    if not patches_dir.exists():
        logger.error(
            "Patches dir not found: %s\nRun Phase 3 first.", patches_dir
        )
        return 1

    md_files = sorted(raw_md_dir.glob("page_*.md"))
    if not md_files:
        logger.error("No page_*.md files in %s", raw_md_dir)
        return 1

    # ── determine mode ────────────────────────────────────────────────────────
    if args.dry_run:
        mode = "dry_run"
    elif args.batch:
        mode = "batch"
    else:
        mode = "interactive"

    # ── accepted change types ─────────────────────────────────────────────────
    accept_types: set[str] | None = None
    if mode == "batch" and not args.accept_all:
        if args.accept_types:
            invalid = set(args.accept_types) - VALID_CHANGE_TYPES
            if invalid:
                logger.error("Unknown change type(s): %s", invalid)
                return 1
            accept_types = set(args.accept_types)
        else:
            # Default safe set for batch with no explicit types
            accept_types = {"punctuation_clean", "space_fix"}
            logger.info(
                "Batch mode with no --accept-types: defaulting to safe types: %s",
                accept_types,
            )

    # ── page list ─────────────────────────────────────────────────────────────
    page_nums = _parse_page_range(args.pages, len(md_files))
    page_nums = [p for p in page_nums if 1 <= p <= len(md_files)]

    logger.info(
        "Mode: %s | Book: %s | Pages: %d | accept_types: %s",
        mode, book_slug, len(page_nums), accept_types or "all",
    )

    applied = skipped = errors = 0
    for page_num in page_nums:
        md_path = raw_md_dir / f"page_{page_num:04d}.md"
        if not md_path.exists():
            logger.warning("page_%04d.md not found – skipping.", page_num)
            skipped += 1
            continue
        try:
            written = apply_page(
                page_num=page_num,
                raw_md=md_path,
                patch_dir=patches_dir,
                verified_md_dir=verified_md_dir,
                mode=mode,
                accept_types=accept_types,
            )
            if written:
                applied += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error("Error applying page %d: %s", page_num, exc)
            errors += 1

    logger.info(
        "Done — applied: %d, skipped: %d, errors: %d", applied, skipped, errors
    )
    if mode != "dry_run":
        logger.info("Verified files written to: %s", verified_md_dir)

    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
