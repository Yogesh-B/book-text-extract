#!/usr/bin/env python3
"""
scripts/run_phase3_verify.py — Phase 3 CLI: LLM verification & patch generation.

Usage (from project root):
  python scripts/run_phase3_verify.py \\
    --book-slug Aadarsh_bhaktgatha \\
    --server-url http://127.0.0.1:8080/v1 \\
    --model-name gemma-4-e2b \\
    [--pages 1-10] \\
    [--force] \\
    [--no-report]

Environment variables (fallbacks):
  LLM_BASE_URL      default: http://127.0.0.1:8080/v1
  LLM_MODEL_NAME    default: gemma-4-e2b
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── make sure src/ is on the path ───────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from src.config import OCR_OUTPUT_DIR, get_ocr_raw_md_dir
from src.phase3_text_verification.llm_client import LLMClient
from src.phase3_text_verification.patch_generator import merge_patches, process_page
from src.phase3_text_verification.report_builder import build_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_phase3_verify")


# ── argument parsing ─────────────────────────────────────────────────────────

def _parse_page_range(spec: str | None, max_page: int) -> list[int]:
    """Parse '1-10', '5', or None (all pages) into a list of 1-based page nums."""
    if spec is None:
        return list(range(1, max_page + 1))
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(spec)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Phase 3: LLM OCR verification & patch generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--book-slug", required=True,
        help="Book slug directory name, e.g. 'Aadarsh_bhaktgatha'",
    )
    p.add_argument(
        "--server-url", default="http://127.0.0.1:8080/v1",
        help="llama-server base URL (default: http://127.0.0.1:8080/v1)",
    )
    p.add_argument(
        "--model-name", default="gemma-4-e2b",
        help="Model name to pass in API requests (default: gemma-4-e2b)",
    )
    p.add_argument(
        "--pages", default=None,
        help="Page range to process, e.g. '1-10' or '5'. Omit for all pages.",
    )
    p.add_argument(
        "--timeout", type=float, default=180,
        help="Per-request timeout in seconds (default: 180)",
    )
    p.add_argument(
        "--max-tokens", type=int, default=4096,
        help="Max tokens for the LLM response (default: 4096)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Re-process pages that already have patch files",
    )
    p.add_argument(
        "--no-report", action="store_true",
        help="Skip generating the HTML summary report",
    )
    return p


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = build_parser().parse_args()

    book_slug: str = args.book_slug
    raw_md_dir = get_ocr_raw_md_dir(book_slug)
    patches_dir = OCR_OUTPUT_DIR / book_slug / "patches"

    # ── validate raw dir ─────────────────────────────────────────────────────
    if not raw_md_dir.exists():
        logger.error(
            "Raw markdown directory not found: %s\n"
            "Run Phase 2 first, or check the book slug.",
            raw_md_dir,
        )
        return 1

    md_files = sorted(raw_md_dir.glob("page_*.md"))
    if not md_files:
        logger.error("No page_XXXX.md files found in %s", raw_md_dir)
        return 1

    patches_dir.mkdir(parents=True, exist_ok=True)

    # ── LLM client health check ───────────────────────────────────────────────
    logger.info("Connecting to LLM server: %s  model: %s", args.server_url, args.model_name)
    client = LLMClient(
        base_url=args.server_url,
        model_name=args.model_name,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
    )
    if not client.health_check():
        logger.error(
            "Cannot reach llama-server at %s.\n"
            "Start it with:  llama-server -m <model.gguf> --port 8080",
            args.server_url,
        )
        return 1

    # ── determine pages to process ────────────────────────────────────────────
    max_page = len(md_files)
    page_nums = _parse_page_range(args.pages, max_page)
    page_nums = [p for p in page_nums if 1 <= p <= max_page]

    logger.info(
        "Processing %d page(s) for book '%s'…",
        len(page_nums), book_slug,
    )

    # ── process pages ─────────────────────────────────────────────────────────
    ok = skipped = errors = 0
    with client:
        for page_num in page_nums:
            md_path = raw_md_dir / f"page_{page_num:04d}.md"
            if not md_path.exists():
                logger.warning("page_%04d.md not found – skipping.", page_num)
                skipped += 1
                continue
            try:
                result = process_page(
                    page_num=page_num,
                    md_path=md_path,
                    patches_dir=patches_dir,
                    client=client,
                    book_slug=book_slug,
                    force=args.force,
                )
                if result is None:
                    skipped += 1
                else:
                    ok += 1
            except Exception as exc:
                logger.error("Error processing page %d: %s", page_num, exc)
                errors += 1

    # ── merge into book_full.patch ────────────────────────────────────────────
    full_patch = patches_dir / "book_full.patch"
    merged = merge_patches(patches_dir, full_patch)
    logger.info("Book patch: %s  (%d page patches merged)", full_patch, merged)

    # ── HTML report ───────────────────────────────────────────────────────────
    if not args.no_report:
        report_path = build_report(book_slug, patches_dir)
        logger.info("HTML report: %s", report_path)

    logger.info(
        "Phase 3 complete — processed: %d, skipped: %d, errors: %d",
        ok, skipped, errors,
    )
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
