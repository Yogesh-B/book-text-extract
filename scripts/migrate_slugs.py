#!/usr/bin/env python3
"""One-time migration: rename data/images/ and data/ocr_output/ folders
from broken slugs (virama/matra stripped) to fixed slugs (marks preserved).

Also updates book_slug inside manifest.json and checkpoint.json files.

Usage:
    python scripts/migrate_slugs.py          # dry run (default)
    python scripts/migrate_slugs.py --apply  # actually rename
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import BOOKS_DIR, IMAGES_DIR, OCR_OUTPUT_DIR, get_book_slug


def old_get_book_slug(pdf_path):
    """Reproduce the OLD broken slug logic for comparison."""
    import re
    stem = Path(pdf_path).stem
    slug = re.sub(r"[^\w]+", "_", stem, flags=re.UNICODE).strip("_")
    return slug or "unnamed_book"


def migrate(apply: bool = False):
    pdfs = sorted(BOOKS_DIR.glob("*.pdf"))
    renames = []  # (data_dir, old_name, new_name)

    for pdf in pdfs:
        old_slug = old_get_book_slug(pdf)
        new_slug = get_book_slug(pdf)

        if old_slug == new_slug:
            continue

        for data_dir in [IMAGES_DIR, OCR_OUTPUT_DIR]:
            old_dir = data_dir / old_slug
            new_dir = data_dir / new_slug
            if old_dir.exists():
                renames.append((data_dir, old_slug, new_slug, old_dir, new_dir))

    if not renames:
        print("Nothing to migrate — all slugs already match.")
        return

    print(f"Found {len(renames)} folder(s) to rename:\n")
    for data_dir, old_slug, new_slug, old_dir, new_dir in renames:
        rel_parent = data_dir.relative_to(PROJECT_ROOT)
        print(f"  {rel_parent}/{old_slug}")
        print(f"    → {rel_parent}/{new_slug}")

        if new_dir.exists():
            print(f"    ⚠ TARGET ALREADY EXISTS — skipping")
            continue

        if apply:
            old_dir.rename(new_dir)
            print(f"    ✓ renamed")

            # Update manifest.json if present
            manifest = new_dir / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    if data.get("book_slug") == old_slug:
                        data["book_slug"] = new_slug
                        manifest.write_text(
                            json.dumps(data, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        print(f"    ✓ updated manifest.json")
                except Exception as e:
                    print(f"    ⚠ failed to update manifest.json: {e}")

            # Update checkpoint.json if present
            checkpoint = new_dir / "checkpoint.json"
            if checkpoint.exists():
                try:
                    data = json.loads(checkpoint.read_text(encoding="utf-8"))
                    if data.get("book_slug") == old_slug:
                        data["book_slug"] = new_slug
                        checkpoint.write_text(
                            json.dumps(data, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        print(f"    ✓ updated checkpoint.json")
                except Exception as e:
                    print(f"    ⚠ failed to update checkpoint.json: {e}")
        print()

    if not apply:
        print(f"\nDry run complete. Run with --apply to rename.")


def main():
    parser = argparse.ArgumentParser(description="Migrate folder slugs after fixing Gujarati slugification.")
    parser.add_argument("--apply", action="store_true", help="Actually rename folders (default is dry run)")
    args = parser.parse_args()
    migrate(apply=args.apply)


if __name__ == "__main__":
    main()
