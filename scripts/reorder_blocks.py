#!/usr/bin/env python3
"""
Post-processing utility: Two-Phase Layout Detection and Top-to-Bottom Reordering.

Takes an IndicOCR output JSON, determines the number of main layout blocks
(1 for single-page scans, 2 for dual-page spreads) using gutter detection,
then sorts each main block top-to-bottom and outputs properly ordered Markdown.

This script delegates all detection/sorting logic to the library module
``src.phase2_indic_ocr.reorder`` so there is a single source of truth.
"""

import importlib.util
import json
import sys
from pathlib import Path

# Add project root to sys.path so the src package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load reorder.py directly to avoid the package __init__ which drags in torch
_REORDER_PATH = PROJECT_ROOT / "src" / "phase2_indic_ocr" / "reorder.py"
_spec = importlib.util.spec_from_file_location("reorder", _REORDER_PATH)
_reorder_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_reorder_mod)

detect_main_blocks = _reorder_mod.detect_main_blocks
reorder_ocr_blocks = _reorder_mod.reorder_ocr_blocks


def main():
    json_path = Path("data/test_output/page_0022.json")
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])

    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    reordered = reorder_ocr_blocks(data)

    # Save reordered files
    stem = json_path.stem
    output_dir = json_path.parent
    out_json = output_dir / f"{stem}_reordered.json"
    out_md = output_dir / f"{stem}_reordered.md"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(reordered, f, ensure_ascii=False, indent=2)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(reordered["markdown"])

    # --- Print reading order comparison table ---
    page_width = float(data.get("width", 3000))
    page_mid = page_width / 2.0
    n_main = reordered.get("layout_main_blocks", "?")

    print("=" * 75)
    print(f"READING ORDER COMPARISON — {json_path.name}")
    print(f"Page width: {page_width:.0f}px  |  Detected main blocks: {n_main}")
    print("=" * 75)
    print(f"{'New#':<5} {'Old#':<5} {'Y-Top':>8} {'Side':<7} {'Snippet'}")
    print("-" * 75)

    for b in reordered["blocks"]:
        old_idx = b.get("detector_order", b.get("old_order", "?"))
        new_idx = b["order"]
        x1, y1, x2, y2 = b["bbox_xyxy"]
        x_center = (x1 + x2) / 2.0
        col_name = "Left" if x_center < page_mid else "Right"
        snippet = b["text"].replace("\n", " ")[:50]
        print(f"{new_idx:<5} {str(old_idx):<5} {y1:>8.1f} {col_name:<7} {snippet}")

    print("=" * 75)
    print(f"✓ Reordered JSON  → {out_json}")
    print(f"✓ Reordered Markdown → {out_md}")
    print("=" * 75)


if __name__ == "__main__":
    main()
