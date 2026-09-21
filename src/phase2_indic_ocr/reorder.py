"""Geometric reading-order reconstruction and main-block detection for IndicOCR outputs.

Scanned books come in two flavours:
  - **Single-page scan**: one physical page per image (e.g. Shri Harikrushna Charitramrut).
  - **Dual-page spread**: two physical pages side-by-side in one image (e.g. Aadarsh Bhaktgatha).

The pipeline is a two-phase process:
  1. **Detect main blocks** — identify whether there is 1 or 2 main content regions on the page
     by looking for a clear vertical gutter near the image centre where no text straddles.
  2. **Sort within each main block** — within each region, sort all sub-blocks top-to-bottom,
     breaking ties left-to-right for elements at the same vertical position (y-tolerance banding).

The previous approach (simple left/right midpoint split) always produced two groups whenever any
block happened to sit right of the image centre (e.g. a small "INDEX" label at the top-right of a
single-page scan), which broke the reading order for single-page layouts.

Key insight for the gutter heuristic
--------------------------------------
In a dual-page spread the binding gutter is a vertical band near the image centre that **no text
block crosses**.  We measure the fraction of blocks that *straddle* a narrow zone centred on the
page midpoint.  If that fraction is high, the page must be a single-page scan (wide body-text
paragraphs naturally straddle the centre of a single page).  Only when blocks cluster clearly on
one side or the other — with very few straddlers — do we call it a dual-page spread.
"""

from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _straddles_gutter(
    block: Dict[str, Any],
    gutter_left: float,
    gutter_right: float,
) -> bool:
    """Return True if the block's horizontal extent crosses the gutter zone.

    A block straddles the gutter when its left edge lies clearly in the left
    region (x1 < gutter_left) **and** its right edge lies clearly in the
    right region (x2 > gutter_right).

    Args:
        block: Block dict with a 'bbox_xyxy' key ([x1, y1, x2, y2]).
        gutter_left: Left boundary of the gutter zone (pixels).
        gutter_right: Right boundary of the gutter zone (pixels).
    """
    x1, _, x2, _ = block["bbox_xyxy"]
    return x1 < gutter_left and x2 > gutter_right


# ---------------------------------------------------------------------------
# Phase 1: Main block detection
# ---------------------------------------------------------------------------

def detect_main_blocks(
    blocks: List[Dict[str, Any]],
    page_width: float,
    width_threshold_ratio: float = 0.8,
    gutter_margin_ratio: float = 0.05,
    min_blocks_per_side: int = 2,
    max_straddle_ratio: float = 0.30,
) -> List[List[Dict[str, Any]]]:
    """Detect whether the page has 1 or 2 main content regions, then group blocks accordingly.

    **Algorithm (Phase 1)**:

    A dual-page spread has a clear binding gutter — a vertical band near the image centre
    that no text block crosses.  We detect this by:

    1. Classifying every valid content block as one of:
       - **left_only**: centre-x < page_mid and does *not* straddle the gutter zone.
       - **right_only**: centre-x ≥ page_mid and does *not* straddle the gutter zone.
       - **straddling**: the block's horizontal extent crosses the gutter zone.

    2. Computing ``straddle_ratio = len(straddling) / len(all_blocks)``.

    3. Declaring a **dual-page spread** only when:
       - ``len(left_only) >= min_blocks_per_side``,
       - ``len(right_only) >= min_blocks_per_side``, AND
       - ``straddle_ratio <= max_straddle_ratio``.

       Wide body-text paragraphs (common in single-page scans) straddle the centre of
       the image, so their presence quickly pushes ``straddle_ratio`` above the threshold
       and prevents a false dual-page detection.

    4. **Dual-page path**: straddling blocks (e.g. spine artefacts) are reassigned to the
       side whose midpoint is nearest, then two groups [left, right] are returned.

    5. **Single-page path**: all valid blocks are returned as a single group.
       Vertical ordering is handled later by :func:`sort_column_blocks`.

    Args:
        blocks: List of block dicts with ``'bbox_xyxy'`` ([x1, y1, x2, y2]) and ``'text'``.
        page_width: Pixel width of the page image.
        width_threshold_ratio: Reserved for future use / backward-compatibility signature
            alignment with :func:`cluster_columns`.  Not used in the detection logic.
        gutter_margin_ratio: Half-width of the gutter zone as a fraction of ``page_width``.
            Default 0.05 → for a 3000 px dual-page image the gutter zone spans
            [1350 px, 1650 px] (±150 px either side of centre).
        min_blocks_per_side: Minimum number of blocks that must sit exclusively on one
            side before that side is considered "populated enough" to declare dual-page.
        max_straddle_ratio: Maximum fraction of blocks allowed to straddle the gutter
            zone while still declaring a dual-page spread.  Higher straddling fractions
            indicate a single-page scan with wide paragraphs.

    Returns:
        A list of 1 or 2 lists of block dicts.  Each inner list represents one main
        block and will be independently sorted by :func:`sort_column_blocks`.
    """
    if not blocks:
        return []

    # Drop blocks without valid bounding boxes or non-empty text
    valid_blocks = [
        b for b in blocks
        if "bbox_xyxy" in b and len(b["bbox_xyxy"]) == 4 and b.get("text", "").strip()
    ]
    if not valid_blocks:
        return []

    # --- Gutter zone centred on the page midpoint ---
    page_mid = page_width / 2.0
    gutter_half = gutter_margin_ratio * page_width
    gutter_left = page_mid - gutter_half
    gutter_right = page_mid + gutter_half

    # --- Classify ALL blocks relative to the gutter ---
    # Wide body-text paragraphs in single-page scans naturally straddle the centre.
    # Including them in the straddle count is intentional: it raises straddle_ratio
    # and correctly prevents false dual-page detection.
    left_only: List[Dict[str, Any]] = []
    right_only: List[Dict[str, Any]] = []
    straddling: List[Dict[str, Any]] = []

    for b in valid_blocks:
        x1, _, x2, _ = b["bbox_xyxy"]
        center_x = (x1 + x2) / 2.0
        if _straddles_gutter(b, gutter_left, gutter_right):
            straddling.append(b)
        elif center_x < page_mid:
            left_only.append(b)
        else:
            right_only.append(b)

    n_total = len(valid_blocks)
    straddle_ratio = len(straddling) / n_total if n_total else 0.0

    is_dual_page = (
        len(left_only) >= min_blocks_per_side
        and len(right_only) >= min_blocks_per_side
        and straddle_ratio <= max_straddle_ratio
    )

    if is_dual_page:
        # Dual-page spread: assign any straddlers (spine artefacts, etc.) to the
        # side whose centre is nearest, then return [left_group, right_group].
        for b in straddling:
            x1, _, x2, _ = b["bbox_xyxy"]
            if (x1 + x2) / 2.0 < page_mid:
                left_only.append(b)
            else:
                right_only.append(b)
        return [left_only, right_only]

    # Single-page: one group — sorting happens in sort_column_blocks
    return [valid_blocks]


# Backward-compatibility alias — scripts/reorder_blocks.py and any external
# callers that imported `cluster_columns` will continue to work unchanged.
def cluster_columns(
    blocks: List[Dict[str, Any]],
    page_width: float,
    width_threshold_ratio: float = 0.8,
) -> List[List[Dict[str, Any]]]:
    """Deprecated alias for :func:`detect_main_blocks`.

    .. deprecated::
        Use :func:`detect_main_blocks` directly for new code.
    """
    return detect_main_blocks(
        blocks=blocks,
        page_width=page_width,
        width_threshold_ratio=width_threshold_ratio,
    )


# ---------------------------------------------------------------------------
# Phase 2: Sort within a single main block
# ---------------------------------------------------------------------------

def sort_column_blocks(
    column_blocks: List[Dict[str, Any]],
    y_tolerance: float = 20.0,
) -> List[Dict[str, Any]]:
    """Sort blocks within a single main block top-to-bottom.

    When two blocks share approximately the same vertical position
    (|y1_a - y1_b| < ``y_tolerance``), they are sorted left-to-right (by x1).
    This keeps side-by-side elements (e.g. a chapter title and a page number on
    the same line) in the correct left→right order.

    Args:
        column_blocks: List of block dicts in one main block.
        y_tolerance: Vertical pixel band to group elements on the same line.

    Returns:
        Sorted list of block dicts.
    """
    def block_sort_key(b: Dict[str, Any]):
        x1, y1, _, _ = b["bbox_xyxy"]
        y_band = round(y1 / y_tolerance) * y_tolerance
        return (y_band, x1)

    return sorted(column_blocks, key=block_sort_key)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def reorder_ocr_blocks(
    result_data: Dict[str, Any],
    y_tolerance: float = 20.0,
) -> Dict[str, Any]:
    """Reorder blocks in an IndicOCR result dictionary into natural reading order.

    Applies the two-phase layout detection:

    1. :func:`detect_main_blocks` — determines whether the page is a single-page
       scan (1 main block) or a dual-page spread (2 main blocks) using a
       gutter-straddling heuristic.
    2. :func:`sort_column_blocks` — within each main block, sorts sub-blocks
       top-to-bottom with left-to-right tie-breaking.

    Produces an updated copy of the result dictionary with:

    - Updated ``'order'`` field on each block (sequential 0 … N-1).
    - Preserved ``'detector_order'`` for auditability.
    - Reconstructed ``'markdown'`` reflecting the clean reading flow.
    - Added ``'layout_main_blocks'`` (int): number of main blocks detected
      (1 = single-page scan, 2 = dual-page spread).

    Args:
        result_data: Raw dictionary returned by IndicOCR parser.
        y_tolerance: Vertical line tolerance in pixels passed to
            :func:`sort_column_blocks`.

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

    # Phase 1 — detect main blocks (1 or 2 groups)
    main_block_groups = detect_main_blocks(non_empty, page_width)

    # Phase 2 — sort within each main block, then concatenate
    ordered_blocks: List[Dict[str, Any]] = []
    for group in main_block_groups:
        sorted_group = sort_column_blocks(group, y_tolerance=y_tolerance)
        ordered_blocks.extend(sorted_group)

    # Assign clean sequential indices and preserve the original detector order
    reordered_blocks: List[Dict[str, Any]] = []
    for new_idx, block in enumerate(ordered_blocks):
        b_copy = dict(block)
        b_copy["detector_order"] = b_copy.get("order")
        b_copy["order"] = new_idx
        reordered_blocks.append(b_copy)

    # Rebuild Markdown in the new reading order
    md_parts = [
        b["text"].strip() for b in reordered_blocks if b.get("text", "").strip()
    ]
    reordered_markdown = "\n\n".join(md_parts)

    reordered_result = dict(result_data)
    reordered_result["blocks"] = reordered_blocks
    reordered_result["markdown"] = reordered_markdown
    reordered_result["reading_order_reordered"] = True
    reordered_result["layout_main_blocks"] = len(main_block_groups)

    return reordered_result
