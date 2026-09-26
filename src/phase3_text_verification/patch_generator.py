"""
patch_generator.py — Diff, unified-patch, and JSON change-log generator.

For each page:
  1. Calls the LLM to get corrected text.
  2. Computes a unified diff (raw → corrected).
  3. Writes a standard .patch file.
  4. Writes a structured JSON change log.

The raw OCR files are NEVER modified.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import (
    GUJARATI_PROOFREADER_SYSTEM_PROMPT,
    build_user_message,
    extract_corrected_text,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PageChange:
    line: int
    type: str
    original: str
    proposed: str
    reason: str


@dataclass
class PageDiff:
    page: int
    raw_path: str           # relative path used in the diff header
    changes_count: int = 0
    changes: list[PageChange] = field(default_factory=list)
    unified_patch: str = ""
    corrected_text: Optional[str] = None   # None → model returned no change
    llm_raw_response: str = ""             # stored for debugging


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _classify_change(orig_line: str, prop_line: str) -> str:
    """Heuristically classify the type of correction."""
    orig_stripped = orig_line.strip()
    prop_stripped = prop_line.strip()

    # Stray leading punctuation removal
    stray = re.match(r"^[?|।\-–—*]+\s*", orig_stripped)
    if stray and prop_stripped == orig_stripped[stray.end():].strip():
        return "punctuation_clean"

    # Pure whitespace change within a word
    if orig_stripped.replace(" ", "") == prop_stripped.replace(" ", ""):
        return "space_fix"

    # Length difference likely means conjunct was joined/split
    if abs(len(orig_stripped) - len(prop_stripped)) <= 3:
        return "conjunct_fix"

    return "spelling_fix"


def _build_page_diff(
    page_num: int,
    raw_text: str,
    corrected_text: str,
    raw_rel_path: str,
    verified_rel_path: str,
) -> PageDiff:
    """Compute unified diff and structured change log between raw and corrected."""
    raw_lines = raw_text.splitlines(keepends=True)
    cor_lines = corrected_text.splitlines(keepends=True)

    unified = list(
        difflib.unified_diff(
            raw_lines,
            cor_lines,
            fromfile=f"a/{raw_rel_path}",
            tofile=f"b/{verified_rel_path}",
            lineterm="",
        )
    )

    # Build structured change log
    changes: list[PageChange] = []
    lineno = 0
    for diff_line in unified:
        if diff_line.startswith("@@"):
            # Parse @@ -start,count +start,count @@
            m = re.search(r"^@@ -(\d+)", diff_line)
            if m:
                lineno = int(m.group(1))
            continue
        if diff_line.startswith("---") or diff_line.startswith("+++"):
            continue

        if diff_line.startswith("-"):
            orig = diff_line[1:].rstrip("\n")
            # Try to find the matching '+' line
            lineno += 1
            changes.append(
                PageChange(
                    line=lineno,
                    type="remove",
                    original=orig,
                    proposed="",
                    reason="Line removed by proofreader",
                )
            )
        elif diff_line.startswith("+"):
            prop = diff_line[1:].rstrip("\n")
            # Patch up the last "remove" if there is one (turned into replace)
            if changes and changes[-1].type == "remove" and changes[-1].proposed == "":
                last = changes[-1]
                last.proposed = prop
                last.type = _classify_change(last.original, prop)
                last.reason = f"OCR correction ({last.type})"
            else:
                changes.append(
                    PageChange(
                        line=lineno,
                        type="insert",
                        original="",
                        proposed=prop,
                        reason="Line inserted by proofreader",
                    )
                )
        else:
            lineno += 1

    patch_str = "\n".join(unified)
    return PageDiff(
        page=page_num,
        raw_path=raw_rel_path,
        changes_count=len(changes),
        changes=changes,
        unified_patch=patch_str,
        corrected_text=corrected_text,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_page(
    page_num: int,
    md_path: Path,
    patches_dir: Path,
    client: LLMClient,
    book_slug: str,
    force: bool = False,
) -> Optional[PageDiff]:
    """
    Run LLM verification for a single page markdown file.

    Writes:
      patches_dir/page_XXXX.patch
      patches_dir/page_XXXX_diff.json

    Returns a PageDiff (or None if skipped / no changes).
    """
    page_tag = f"page_{page_num:04d}"
    patch_file = patches_dir / f"{page_tag}.patch"
    json_file = patches_dir / f"{page_tag}_diff.json"

    # Skip if already done (unless forced)
    if not force and patch_file.exists() and json_file.exists():
        logger.info("[%s] Already processed – skipping.", page_tag)
        return None

    raw_text = md_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        logger.warning("[%s] Empty markdown – skipping.", page_tag)
        return None

    # ── call LLM ────────────────────────────────────────────────────────────
    user_msg = build_user_message(page_num, raw_text)
    logger.info("[%s] Sending to LLM (%d chars)…", page_tag, len(raw_text))
    llm_response = client.complete(GUJARATI_PROOFREADER_SYSTEM_PROMPT, user_msg)

    corrected = extract_corrected_text(llm_response)
    if corrected is None:
        logger.warning(
            "[%s] Model did not return a ```gujarati``` block. Raw response:\n%s",
            page_tag, llm_response[:500],
        )
        # Still write an empty diff so the page is marked "done"
        page_diff = PageDiff(
            page=page_num,
            raw_path=f"{book_slug}/raw/markdown/{page_tag}.md",
            llm_raw_response=llm_response,
        )
        _write_outputs(page_diff, patch_file, json_file)
        return page_diff

    # ── compute diff ────────────────────────────────────────────────────────
    raw_rel = f"{book_slug}/raw/markdown/{page_tag}.md"
    ver_rel = f"{book_slug}/verified/markdown/{page_tag}.md"
    page_diff = _build_page_diff(page_num, raw_text, corrected, raw_rel, ver_rel)
    page_diff.llm_raw_response = llm_response

    logger.info(
        "[%s] Done – %d change(s) found.", page_tag, page_diff.changes_count
    )

    _write_outputs(page_diff, patch_file, json_file)
    return page_diff


def _write_outputs(page_diff: PageDiff, patch_file: Path, json_file: Path) -> None:
    """Write .patch and _diff.json for a page."""
    patch_file.parent.mkdir(parents=True, exist_ok=True)

    # .patch file
    patch_file.write_text(page_diff.unified_patch or "", encoding="utf-8")

    # _diff.json
    payload = {
        "page": page_diff.page,
        "raw_path": page_diff.raw_path,
        "changes_count": page_diff.changes_count,
        "changes": [
            {
                "line": c.line,
                "type": c.type,
                "original": c.original,
                "proposed": c.proposed,
                "reason": c.reason,
            }
            for c in page_diff.changes
        ],
    }
    json_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def merge_patches(patches_dir: Path, output_patch: Path) -> int:
    """
    Concatenate all per-page .patch files into one book_full.patch.

    Returns the total number of page patches merged.
    """
    patch_files = sorted(patches_dir.glob("page_*.patch"))
    combined: list[str] = []
    for pf in patch_files:
        content = pf.read_text(encoding="utf-8").strip()
        if content:
            combined.append(content)

    output_patch.write_text("\n\n".join(combined) + "\n", encoding="utf-8")
    logger.info("Merged %d patches → %s", len(combined), output_patch)
    return len(combined)
