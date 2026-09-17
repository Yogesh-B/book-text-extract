"""Geometric reading-order reconstruction and column clustering for IndicOCR outputs.

Scanned books often have two-page spreads or multi-column layouts.
Raw bounding-box detections may interleave left and right columns.
This module clusters blocks horizontally and sorts them vertically top-to-bottom.
"""

from typing import Any, Dict, List


def cluster_columns(
    blocks: List[Dict[str, Any]],
    page_width: float,
    width_threshold_ratio: float = 0.8,
) -> List[List[Dict[str, Any]]]:
    """Cluster blocks into layout columns (e.g. Left and Right columns/pages).

    Blocks spanning almost the entire width (> width_threshold_ratio * page_width)
    are treated as full-width headers or banners.

    Args:
        blocks: List of block dictionaries containing 'bbox_xyxy' and 'text'.
        page_width: Pixel width of the page image.
        width_threshold_ratio: Fraction of page width above which a block is full-width.

    Returns:
        A list of columns, where each column is a list of block dicts.
    """
    if not blocks:
        return []

    # Filter out blocks without bounding boxes or meaningful text
    valid_blocks = [
        b for b in blocks
        if "bbox_xyxy" in b and len(b["bbox_xyxy"]) == 4 and b.get("text", "").strip()
    ]
    if not valid_blocks:
        return []

    content_blocks = []
    full_width_headers = []

    for b in valid_blocks:
        x1, y1, x2, y2 = b["bbox_xyxy"]
        w = x2 - x1
        if w > width_threshold_ratio * page_width:
            full_width_headers.append(b)
        else:
            content_blocks.append(b)

    if not content_blocks:
        full_width_headers.sort(key=lambda b: (b["bbox_xyxy"][1], b["bbox_xyxy"][0]))
        return [full_width_headers]

    page_mid = page_width / 2.0

    # Determine if there are blocks distinctly on both sides of the page midpoint
    left_blocks = [
        b for b in content_blocks
        if (b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0 < page_mid
    ]
    right_blocks = [
        b for b in content_blocks
        if (b["bbox_xyxy"][0] + b["bbox_xyxy"][2]) / 2.0 >= page_mid
    ]

    columns: List[List[Dict[str, Any]]] = []
    # If both sides contain content, treat as dual-column / double-page spread
    if left_blocks and right_blocks:
        columns.append(left_blocks)
        columns.append(right_blocks)
    else:
        columns.append(content_blocks)

    # If full width headers exist at top/bottom, preserve them logically
    if full_width_headers:
        top_headers = [b for b in full_width_headers if b["bbox_xyxy"][1] < content_blocks[0]["bbox_xyxy"][1]]
        bottom_headers = [b for b in full_width_headers if b not in top_headers]
        if top_headers:
            columns.insert(0, top_headers)
        if bottom_headers:
            columns.append(bottom_headers)

    return columns


def sort_column_blocks(
    column_blocks: List[Dict[str, Any]],
    y_tolerance: float = 20.0,
) -> List[Dict[str, Any]]:
    """Sort blocks within a single column top-to-bottom.

    When two blocks share approximately the same vertical position
    (|y1_a - y1_b| < y_tolerance), they are sorted left-to-right (by x1).

    Args:
        column_blocks: List of block dicts in one column.
        y_tolerance: Vertical pixel band to group elements on the same line.

    Returns:
        Sorted list of block dicts.
    """
    def block_sort_key(b: Dict[str, Any]):
        x1, y1, _, _ = b["bbox_xyxy"]
        y_band = round(y1 / y_tolerance) * y_tolerance
        return (y_band, x1)

    return sorted(column_blocks, key=block_sort_key)


def reorder_ocr_blocks(
    result_data: Dict[str, Any],
    y_tolerance: float = 20.0,
) -> Dict[str, Any]:
    """Reorder blocks in IndicOCR result dictionary into natural reading order.

    Produces an updated copy of the result dictionary with:
    - Updated 'order' field on each block (sequential 0..N-1).
    - Preserved 'detector_order' for auditability.
    - Reconstructed 'markdown' reflecting the clean reading flow.

    Args:
        result_data: Raw dictionary returned by IndicOCR parser.
        y_tolerance: Vertical line tolerance in pixels.

    Returns:
        New dictionary with reordered blocks and updated Markdown.
    """
    page_width = float(result_data.get("width", 3000))
    raw_blocks = result_data.get("blocks", [])

    if not raw_blocks:
        return dict(result_data)

    # Extract non-empty text blocks
    non_empty = [
        b for b in raw_blocks
        if "bbox_xyxy" in b and len(b["bbox_xyxy"]) == 4 and b.get("text", "").strip()
    ]

    if not non_empty:
        return dict(result_data)

    columns = cluster_columns(non_empty, page_width)

    ordered_blocks: List[Dict[str, Any]] = []
    for col in columns:
        sorted_col = sort_column_blocks(col, y_tolerance=y_tolerance)
        ordered_blocks.extend(sorted_col)

    # Assign clean sequential indices
    reordered_blocks: List[Dict[str, Any]] = []
    for new_idx, block in enumerate(ordered_blocks):
        b_copy = dict(block)
        b_copy["detector_order"] = b_copy.get("order")
        b_copy["order"] = new_idx
        reordered_blocks.append(b_copy)

    # Rebuild Markdown
    md_parts = [
        b["text"].strip() for b in reordered_blocks
        if b.get("text", "").strip()
    ]
    reordered_markdown = "\n\n".join(md_parts)

    reordered_result = dict(result_data)
    reordered_result["blocks"] = reordered_blocks
    reordered_result["markdown"] = reordered_markdown
    reordered_result["reading_order_reordered"] = True

    return reordered_result
