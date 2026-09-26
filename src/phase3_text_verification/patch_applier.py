"""
patch_applier.py — Apply verified patches into the verified/ directory.

Supports three modes:
  - batch  : apply all patches without asking
  - interactive : prompt [y/n/a/q] per hunk
  - dry_run: preview only, no files written
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ApplyMode = Literal["batch", "interactive", "dry_run"]


def _load_diff_json(json_file: Path) -> dict:
    try:
        return json.loads(json_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_page(
    page_num: int,
    raw_md: Path,
    patch_dir: Path,
    verified_md_dir: Path,
    mode: ApplyMode = "interactive",
    accept_types: set[str] | None = None,
) -> bool:
    """
    Apply a single page patch.

    Parameters
    ----------
    accept_types : if given (batch mode), only auto-accept changes whose
                   `type` is in this set (e.g. {'punctuation_clean', 'space_fix'}).
                   None means accept all in batch mode.

    Returns True if the verified file was written, False if skipped.
    """
    page_tag = f"page_{page_num:04d}"
    diff_json_path = patch_dir / f"{page_tag}_diff.json"
    patch_path = patch_dir / f"{page_tag}.patch"

    if not patch_path.exists():
        logger.warning("[%s] No patch file found – skipping.", page_tag)
        return False

    diff_data = _load_diff_json(diff_json_path)
    changes = diff_data.get("changes", [])

    if not changes:
        # No changes – copy raw to verified unchanged
        _copy_to_verified(raw_md, verified_md_dir, page_tag)
        logger.info("[%s] No changes – copied raw as verified.", page_tag)
        return True

    raw_lines = raw_md.read_text(encoding="utf-8").splitlines(keepends=True)

    if mode == "dry_run":
        print(f"\n{'─'*60}")
        print(f"[DRY RUN] {page_tag} – {len(changes)} change(s)")
        for ch in changes:
            print(f"  Line {ch['line']:4d} [{ch['type']}]")
            print(f"    - {ch['original']!r}")
            print(f"    + {ch['proposed']!r}")
            print(f"    ℹ {ch['reason']}")
        return False

    # ── Build accepted set ───────────────────────────────────────────────────
    accepted_changes: list[dict] = []

    if mode == "batch":
        for ch in changes:
            if accept_types is None or ch["type"] in accept_types:
                accepted_changes.append(ch)
            else:
                logger.info(
                    "[%s] Batch skipped change type '%s' at line %d",
                    page_tag, ch["type"], ch["line"],
                )
    else:  # interactive
        print(f"\n{'═'*60}")
        print(f"[Page {page_num}] – {len(changes)} proposed change(s)")
        accept_all = False
        quit_all = False

        for idx, ch in enumerate(changes, 1):
            if quit_all:
                break
            if accept_all:
                accepted_changes.append(ch)
                continue

            print(f"\n  [{idx}/{len(changes)}] Line {ch['line']} [{ch['type']}]")
            print(f"    - {ch['original']!r}")
            print(f"    + {ch['proposed']!r}")
            print(f"    ℹ  {ch['reason']}")

            while True:
                ans = input("  Apply? [y]es / [n]o / [a]ll remaining / [q]uit > ").strip().lower()
                if ans in ("y", "yes"):
                    accepted_changes.append(ch)
                    break
                elif ans in ("n", "no"):
                    break
                elif ans in ("a", "all"):
                    accepted_changes.append(ch)
                    accept_all = True
                    break
                elif ans in ("q", "quit"):
                    quit_all = True
                    break
                else:
                    print("  Please enter y / n / a / q")

    if not accepted_changes and mode == "interactive":
        print(f"[{page_tag}] No changes accepted – skipped.")
        return False

    # ── Apply accepted changes to raw lines ──────────────────────────────────
    verified_lines = list(raw_lines)

    for ch in accepted_changes:
        lineno = ch["line"] - 1  # 0-indexed
        ch_type = ch["type"]
        proposed = ch["proposed"]

        if lineno < 0 or lineno >= len(verified_lines):
            logger.warning("[%s] Change at line %d out of range", page_tag, ch["line"])
            continue

        if ch_type in ("remove",):
            if ch["proposed"] == "":
                verified_lines[lineno] = ""
            else:
                verified_lines[lineno] = proposed + "\n"
        elif ch_type == "insert":
            verified_lines.insert(lineno, proposed + "\n")
        else:
            # replace (conjunct_fix, space_fix, punctuation_clean, spelling_fix)
            eol = "\n" if verified_lines[lineno].endswith("\n") else ""
            verified_lines[lineno] = proposed + eol

    # Remove blank lines that were deleted (empty string entries)
    verified_lines = [ln for ln in verified_lines if ln != ""]

    verified_text = "".join(verified_lines)
    out_path = _write_verified(verified_text, verified_md_dir, page_tag)
    logger.info("[%s] Written verified → %s", page_tag, out_path)
    return True


def _copy_to_verified(raw_md: Path, verified_md_dir: Path, page_tag: str) -> Path:
    verified_md_dir.mkdir(parents=True, exist_ok=True)
    dest = verified_md_dir / f"{page_tag}.md"
    shutil.copy2(raw_md, dest)
    return dest


def _write_verified(text: str, verified_md_dir: Path, page_tag: str) -> Path:
    verified_md_dir.mkdir(parents=True, exist_ok=True)
    dest = verified_md_dir / f"{page_tag}.md"
    dest.write_text(text, encoding="utf-8")
    return dest
