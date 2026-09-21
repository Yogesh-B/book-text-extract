"""Unit tests for src/phase2_indic_ocr/reorder.py — two-phase layout detection.

Imports the reorder module directly (without going through the package __init__)
 so that torch is not required just to run the pure-geometry tests.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load reorder.py directly so we avoid the package __init__ which drags in torch
_REORDER_PATH = PROJECT_ROOT / "src" / "phase2_indic_ocr" / "reorder.py"
_spec = importlib.util.spec_from_file_location("reorder", _REORDER_PATH)
_reorder_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_reorder_mod)

cluster_columns = _reorder_mod.cluster_columns
detect_main_blocks = _reorder_mod.detect_main_blocks
reorder_ocr_blocks = _reorder_mod.reorder_ocr_blocks
sort_column_blocks = _reorder_mod.sort_column_blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_block(order: int, x1: float, y1: float, x2: float, y2: float, text: str = "text") -> Dict[str, Any]:
    """Create a minimal block dict as IndicOCR would produce."""
    return {
        "order": order,
        "bbox_xyxy": [x1, y1, x2, y2],
        "text": text,
    }


def make_result(blocks: List[Dict[str, Any]], width: int = 1449, height: int = 2481) -> Dict[str, Any]:
    """Wrap blocks in a minimal IndicOCR result dict."""
    return {
        "width": width,
        "height": height,
        "blocks": blocks,
        "markdown": "",
    }


# ---------------------------------------------------------------------------
# detect_main_blocks
# ---------------------------------------------------------------------------

class TestDetectMainBlocks:
    """Tests for the Phase-1 main block detector."""

    def test_empty_blocks_returns_empty(self):
        result = detect_main_blocks([], page_width=1449)
        assert result == []

    def test_blank_text_blocks_ignored(self):
        blocks = [make_block(0, 100, 100, 400, 200, text="   ")]
        result = detect_main_blocks(blocks, page_width=1449)
        assert result == []

    # --- Single-page layouts ---

    def test_single_page_all_straddling(self):
        """Blocks spanning the full width → single main block."""
        # page_width=1449, all blocks span from 50→1400 (straddle mid=724.5±72)
        blocks = [
            make_block(i, 50, i * 300, 1400, (i + 1) * 300, text=f"Para {i}")
            for i in range(4)
        ]
        groups = detect_main_blocks(blocks, page_width=1449)
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"
        assert len(groups[0]) == 4

    def test_single_page_with_right_label(self):
        """A small right-side label (like INDEX) must NOT trigger dual-page detection."""
        # Mimics real page_0003.json / page_0013.json pattern:
        #   main body: straddles or left-of-mid
        #   INDEX label: right side, narrow
        #   page number: right side, narrow
        blocks = [
            make_block(0, 83, 174, 1055, 434, text="Title text"),         # left-ish, not straddling
            make_block(1, 115, 444, 1406, 1255, text="Main body"),         # straddles
            make_block(2, 566, 1264, 998, 1378, text=": Praptisthan :"),   # right-of-mid, narrow
            make_block(3, 148, 1382, 1294, 2349, text="Contact list"),     # straddles
            make_block(4, 1107, 36, 1389, 131, text="INDEX"),              # right, narrow
        ]
        groups = detect_main_blocks(blocks, page_width=1449)
        assert len(groups) == 1, (
            f"Single-page with INDEX label should yield 1 main block, got {len(groups)}: "
            f"{[[b['text'] for b in g] for g in groups]}"
        )

    def test_single_page_mixed_positions(self):
        """Left + right blocks, but some straddle — should be 1 main block."""
        # 2 left, 1 right, 2 straddling → straddle_ratio = 2/5 = 0.40 > 0.30
        blocks = [
            make_block(0, 50, 100, 600, 300, text="Left 1"),     # left_only
            make_block(1, 50, 310, 600, 500, text="Left 2"),     # left_only
            make_block(2, 900, 100, 1400, 300, text="Right 1"),  # right_only
            make_block(3, 50, 510, 1400, 700, text="Straddle 1"),# straddles
            make_block(4, 50, 710, 1400, 900, text="Straddle 2"),# straddles
        ]
        groups = detect_main_blocks(blocks, page_width=1449)
        assert len(groups) == 1

    # --- Dual-page spread layouts ---

    def test_dual_page_spread(self):
        """Clear left/right split with no straddling → 2 main blocks."""
        # Simulate Aadarsh Bhaktgatha: page_width=3000, left page x<1400, right page x>1600
        pw = 3000
        left = [
            make_block(i, 100, i * 200, 1400, (i + 1) * 200, text=f"Left block {i}")
            for i in range(5)
        ]
        right = [
            make_block(10 + i, 1600, i * 200, 2900, (i + 1) * 200, text=f"Right block {i}")
            for i in range(5)
        ]
        groups = detect_main_blocks(left + right, page_width=pw)
        assert len(groups) == 2, f"Expected 2 groups (dual-page), got {len(groups)}"
        # All left blocks should be in group 0
        group0_texts = {b["text"] for b in groups[0]}
        assert all(f"Left block {i}" in group0_texts for i in range(5))
        # All right blocks should be in group 1
        group1_texts = {b["text"] for b in groups[1]}
        assert all(f"Right block {i}" in group1_texts for i in range(5))

    def test_dual_page_left_then_right_order(self):
        """Left main block must come before right main block in the output groups."""
        pw = 3000
        # Need >= min_blocks_per_side (2) on each side for dual-page to be detected
        left_blocks = [
            make_block(99, 100, 300, 1400, 500, text="Left page content A"),
            make_block(98, 100, 600, 1400, 800, text="Left page content B"),
        ]
        right_blocks = [
            make_block(0, 1600, 100, 2900, 400, text="Right page content A"),
            make_block(1, 1600, 500, 2900, 700, text="Right page content B"),
        ]
        groups = detect_main_blocks(right_blocks + left_blocks, page_width=pw)
        assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
        # All left blocks must be in group[0], all right in group[1]
        group0_texts = {b["text"] for b in groups[0]}
        group1_texts = {b["text"] for b in groups[1]}
        assert "Left page content A" in group0_texts
        assert "Left page content B" in group0_texts
        assert "Right page content A" in group1_texts
        assert "Right page content B" in group1_texts

    def test_dual_page_min_blocks_per_side_not_met(self):
        """If one side has fewer than min_blocks_per_side, treat as single-page."""
        pw = 3000
        left = [make_block(i, 100, i * 200, 1400, (i + 1) * 200, text=f"L{i}") for i in range(5)]
        right = [make_block(10, 1600, 100, 2900, 300, text="R0")]  # only 1 right block
        groups = detect_main_blocks(left + right, page_width=pw)
        # min_blocks_per_side=2, only 1 right block → single main block
        assert len(groups) == 1

    # --- Full-width banner handling ---

    def test_full_width_banner_single_group(self):
        """Full-width banner and body text are single-page → one group, sorted vertically."""
        pw = 1449
        # Both straddle the centre → single-page → all in one group
        banner = make_block(0, 0, 10, 1449, 100, text="Full Width Header")
        body = make_block(1, 50, 200, 1399, 400, text="Body")
        groups = detect_main_blocks([body, banner], page_width=pw)
        assert len(groups) == 1, "Full-width + body should be single main block"
        assert len(groups[0]) == 2
        # Ordering is done by sort_column_blocks (called from reorder_ocr_blocks).
        # Verify via the full pipeline: banner (y=10) must come before body (y=200).
        result = reorder_ocr_blocks(make_result([body, banner], width=pw))
        texts = [b["text"] for b in result["blocks"]]
        assert texts[0] == "Full Width Header"
        assert texts[1] == "Body"

    def test_full_width_only_blocks(self):
        """When all blocks are full-width, they form a single group; vertical order via pipeline."""
        pw = 1449
        blocks = [
            make_block(0, 0, 500, 1449, 600, text="Footer"),
            make_block(1, 0, 100, 1449, 200, text="Header"),
        ]
        groups = detect_main_blocks(blocks, page_width=pw)
        assert len(groups) == 1, "Full-width-only page should be single main block"
        assert len(groups[0]) == 2
        # Ordering is handled by sort_column_blocks; verify through full pipeline.
        result = reorder_ocr_blocks(make_result(blocks, width=pw))
        texts = [b["text"] for b in result["blocks"]]
        # Header (y1=100) must precede Footer (y1=500)
        assert texts.index("Header") < texts.index("Footer")


# ---------------------------------------------------------------------------
# sort_column_blocks
# ---------------------------------------------------------------------------

class TestSortColumnBlocks:
    """Tests for Phase-2 within-block sorting."""

    def test_sort_top_to_bottom(self):
        blocks = [
            make_block(0, 100, 800, 400, 900, text="C"),
            make_block(1, 100, 100, 400, 200, text="A"),
            make_block(2, 100, 400, 400, 500, text="B"),
        ]
        sorted_blocks = sort_column_blocks(blocks, y_tolerance=20.0)
        assert [b["text"] for b in sorted_blocks] == ["A", "B", "C"]

    def test_same_y_sorted_left_to_right(self):
        """Blocks on the same line (within y_tolerance) sort left-to-right."""
        blocks = [
            make_block(0, 800, 100, 1000, 200, text="Right"),   # same y-band
            make_block(1, 100, 105, 400, 205, text="Left"),     # |105-100|=5 < 20 → same band
        ]
        sorted_blocks = sort_column_blocks(blocks, y_tolerance=20.0)
        assert sorted_blocks[0]["text"] == "Left"
        assert sorted_blocks[1]["text"] == "Right"

    def test_empty_list(self):
        assert sort_column_blocks([], y_tolerance=20.0) == []


# ---------------------------------------------------------------------------
# reorder_ocr_blocks — end-to-end
# ---------------------------------------------------------------------------

class TestReorderOcrBlocks:
    """Integration tests for the full reorder_ocr_blocks() pipeline."""

    def test_empty_result(self):
        result = reorder_ocr_blocks({"width": 1449, "height": 2481, "blocks": []})
        assert result["blocks"] == []

    def test_sequential_order_field(self):
        """Output blocks must have sequential 0-based order field."""
        blocks = [
            make_block(5, 50, 200, 1400, 400, text="B"),
            make_block(3, 50, 50, 1400, 150, text="A"),
        ]
        result = reorder_ocr_blocks(make_result(blocks))
        orders = [b["order"] for b in result["blocks"]]
        assert orders == list(range(len(orders)))

    def test_detector_order_preserved(self):
        """Original detector order must be stored in detector_order field."""
        blocks = [
            make_block(7, 50, 200, 1400, 400, text="Second"),
            make_block(2, 50, 50, 1400, 150, text="First"),
        ]
        result = reorder_ocr_blocks(make_result(blocks))
        # First block in reading order should have detector_order=2 (original)
        assert result["blocks"][0]["text"] == "First"
        assert result["blocks"][0]["detector_order"] == 2

    def test_markdown_rebuilt(self):
        """Markdown must reflect the new reading order."""
        blocks = [
            make_block(0, 50, 300, 1400, 400, text="Second paragraph"),
            make_block(1, 50, 50, 1400, 200, text="First paragraph"),
        ]
        result = reorder_ocr_blocks(make_result(blocks))
        md = result["markdown"]
        assert md.index("First paragraph") < md.index("Second paragraph")

    def test_reading_order_reordered_flag(self):
        blocks = [make_block(0, 50, 50, 1400, 200, text="Content")]
        result = reorder_ocr_blocks(make_result(blocks))
        assert result["reading_order_reordered"] is True

    def test_layout_main_blocks_field_single(self):
        """Single-page layout must report layout_main_blocks=1."""
        # All straddling blocks → single main block
        blocks = [
            make_block(i, 50, i * 300, 1400, (i + 1) * 300, text=f"P{i}")
            for i in range(3)
        ]
        result = reorder_ocr_blocks(make_result(blocks, width=1449))
        assert result.get("layout_main_blocks") == 1

    def test_layout_main_blocks_field_dual(self):
        """Dual-page spread must report layout_main_blocks=2."""
        pw = 3000
        left = [make_block(i, 100, i * 200, 1400, (i + 1) * 200, text=f"L{i}") for i in range(3)]
        right = [make_block(10 + i, 1600, i * 200, 2900, (i + 1) * 200, text=f"R{i}") for i in range(3)]
        result = reorder_ocr_blocks(make_result(left + right, width=pw))
        assert result.get("layout_main_blocks") == 2

    def test_real_page_0013_single_page(self):
        """Regression: page_0013.json from Harikrushna book must detect as single-page."""
        json_path = (
            PROJECT_ROOT
            / "data/ocr_output/72181_Shri_Harikrushna_Charitramrut_Sagar_Bhag_1/raw/json/page_0013.json"
        )
        if not json_path.exists():
            pytest.skip("page_0013.json not present in test environment")
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
        result = reorder_ocr_blocks(raw)
        assert result["layout_main_blocks"] == 1, (
            "page_0013 is a single-page scan; dual-page was incorrectly detected"
        )
        # INDEX block should appear BEFORE the main body paragraphs
        texts = [b["text"].strip() for b in result["blocks"]]
        index_pos = next((i for i, t in enumerate(texts) if "INDEX" in t), None)
        assert index_pos is not None, "INDEX block not found"
        # INDEX is at top-right (y≈36) and should be among the first blocks
        assert index_pos < 3, f"INDEX appeared at position {index_pos}, expected near top"


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

class TestClusterColumnsAlias:
    """cluster_columns() must behave identically to detect_main_blocks()."""

    def test_alias_single_page(self):
        blocks = [make_block(i, 50, i * 300, 1400, (i + 1) * 300, text=f"P{i}") for i in range(3)]
        assert cluster_columns(blocks, page_width=1449) == detect_main_blocks(blocks, page_width=1449)

    def test_alias_dual_page(self):
        left = [make_block(i, 100, i * 200, 1400, (i + 1) * 200, text=f"L{i}") for i in range(3)]
        right = [make_block(10 + i, 1600, i * 200, 2900, (i + 1) * 200, text=f"R{i}") for i in range(3)]
        assert (
            cluster_columns(left + right, page_width=3000)
            == detect_main_blocks(left + right, page_width=3000)
        )
