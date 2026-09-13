#!/usr/bin/env python3
"""
Post-processing utility: Column Clustering and Top-to-Bottom (Y-top) Reordering.
Takes an IndicOCR output JSON, reconstructs the reading order geometrically,
and outputs properly ordered Markdown.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

def cluster_columns(blocks: List[Dict[str, Any]], page_width: float) -> List[List[Dict[str, Any]]]:
    """
    Cluster blocks into columns (e.g., Left Page/Column and Right Page/Column).
    Identifies column gutters by finding natural horizontal separation.
    """
    if not blocks:
        return []

    # Filter out empty blocks
    valid_blocks = [b for b in blocks if b.get("text", "").strip()]
    if not valid_blocks:
        return []

    # Check horizontal midpoints and spans
    # For scanned books/spreads, content blocks have width typically < 75% of page width
    content_blocks = []
    full_width_headers = []
    
    for b in valid_blocks:
        x1, y1, x2, y2 = b["bbox_xyxy"]
        w = x2 - x1
        if w > 0.8 * page_width:
            full_width_headers.append(b)
        else:
            content_blocks.append(b)

    if not content_blocks:
        # Only full width blocks
        full_width_headers.sort(key=lambda b: (b["bbox_xyxy"][1], b["bbox_xyxy"][0]))
        return [full_width_headers]

    # Find column boundaries using horizontal centers
    centers = [(b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0 for b in content_blocks]
    min_x = min(b["bbox_xyxy"][0] for b in content_blocks)
    max_x = max(b["bbox_xyxy"][2] for b in content_blocks)
    page_mid = page_width / 2.0

    # Determine if this is a multi-column or double-page spread:
    # Check if there are blocks distinctly to the left and right of the midpoint
    left_blocks = [b for b in content_blocks if (b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0 < page_mid]
    right_blocks = [b for b in content_blocks if (b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0 >= page_mid]

    columns = []
    if left_blocks and right_blocks:
        # 2-column or 2-page spread
        columns = [left_blocks, right_blocks]
    else:
        # Single column
        columns = [content_blocks]

    return columns

def sort_column_blocks(column_blocks: List[Dict[str, Any]], y_tolerance: float = 20.0) -> List[Dict[str, Any]]:
    """
    Sort blocks in a column top-to-bottom (by y1).
    If two blocks share approximately the same vertical line (|y1 - y2| < y_tolerance),
    sort them left-to-right (by x1), such as a header title and page number side-by-side.
    """
    def block_key(b):
        x1, y1, x2, y2 = b["bbox_xyxy"]
        # Bucket y into bands of y_tolerance to keep side-by-side elements on same line
        y_band = round(y1 / y_tolerance) * y_tolerance
        return (y_band, x1)

    return sorted(column_blocks, key=block_key)

def reorder_ocr_blocks(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reorder blocks in JSON data by column clustering and Y-top sorting.
    Returns new JSON structure with updated 'order' and reconstructed 'markdown'.
    """
    page_width = float(json_data.get("width", 3000))
    raw_blocks = json_data.get("blocks", [])

    # Filter empty blocks
    non_empty = [b for b in raw_blocks if b.get("text", "").strip()]

    # Cluster into columns
    columns = cluster_columns(non_empty, page_width)

    # Sort each column top-to-bottom
    ordered_blocks = []
    for col in columns:
        sorted_col = sort_column_blocks(col)
        ordered_blocks.extend(sorted_col)

    # Assign new sequential order
    reordered_blocks = []
    for new_idx, block in enumerate(ordered_blocks):
        b_copy = dict(block)
        b_copy["old_order"] = b_copy.get("order")
        b_copy["order"] = new_idx
        reordered_blocks.append(b_copy)

    # Rebuild markdown
    md_parts = [b["text"].strip() for b in reordered_blocks if b.get("text", "").strip()]
    reordered_markdown = "\n\n".join(md_parts)

    result = dict(json_data)
    result["blocks"] = reordered_blocks
    result["markdown"] = reordered_markdown
    return result

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

    print("=" * 70)
    print("READING ORDER COMPARISON (Old Order vs Reordered)")
    print("=" * 70)
    print(f"{'New #':<6} {'Old #':<6} {'Y-Top (px)':<12} {'Col':<6} {'Snippet'}")
    print("-" * 70)
    
    mid = data.get("width", 3000) / 2.0
    for b in reordered["blocks"]:
        old_idx = b["old_order"]
        new_idx = b["order"]
        y_top = b["bbox_xyxy"][1]
        x_center = (b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0
        col_name = "Left" if x_center < mid else "Right"
        snippet = b["text"].replace("\n", " ")[:45]
        print(f"{new_idx:<6} {old_idx:<6} {y_top:<12.1f} {col_name:<6} {snippet}...")

    print("=" * 70)
    print(f"✓ Saved reordered JSON to: {out_json}")
    print(f"✓ Saved reordered Markdown to: {out_md}")
    print("=" * 70)

if __name__ == "__main__":
    main()
