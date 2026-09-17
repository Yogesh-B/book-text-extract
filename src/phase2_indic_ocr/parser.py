"""IndicOCR document parser and transcription wrapper.

Integrates PP-DocLayoutV3 block layout parsing with Qwen3.5/Sarvam Gujarati OCR,
applying geometric column reordering to produce clean structured JSON and Markdown.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.phase2_indic_ocr.model_loader import load_indic_ocr
from src.phase2_indic_ocr.reorder import reorder_ocr_blocks
from src.utils.logger import get_logger

logger = get_logger("indic_parser")


class IndicOCRParser:
    """High-level wrapper around the IndicOCR model."""

    def __init__(
        self,
        model_path: Optional[Path | str] = None,
        device: Optional[str] = None,
        engine: Optional[Any] = None,
        compile_model: bool = False,
    ):
        """Initialize IndicOCR parser.

        Args:
            model_path: Path to indic-ocr directory. If None, auto-discovered.
            device: 'cuda' or 'cpu'.
            engine: Optional pre-loaded IndicOCR instance.
            compile_model: Whether to optimize recognizer using torch.compile(dynamic=True).
        """
        if engine is not None:
            self.engine = engine
        else:
            self.engine = load_indic_ocr(
                model_path=model_path,
                device=device,
                compile_model=compile_model,
            )

    def parse_page(
        self,
        image_path: Path | str,
        reorder: bool = True,
        y_tolerance: float = 20.0,
    ) -> Dict[str, Any]:
        """Parse a single page image.

        Args:
            image_path: Path to PNG/JPEG page image.
            reorder: Whether to apply column clustering & top-to-bottom reordering.
            y_tolerance: Vertical line tolerance for sorting side-by-side elements.

        Returns:
            Dictionary containing 'blocks', 'markdown', page dimensions, and timing info.
        """
        img_path = Path(image_path).resolve()
        if not img_path.exists():
            raise FileNotFoundError(f"Page image not found: {img_path}")

        t0 = time.time()
        raw_result = self.engine.parse(str(img_path))
        inference_time = time.time() - t0

        if reorder:
            result = reorder_ocr_blocks(raw_result, y_tolerance=y_tolerance)
        else:
            result = dict(raw_result)
            result["reading_order_reordered"] = False

        result["image_name"] = img_path.name
        result["image_path"] = str(img_path)
        result["inference_duration_sec"] = round(inference_time, 2)

        return result

    @staticmethod
    def save_page_output(
        result: Dict[str, Any],
        page_num: int,
        json_dir: Path,
        md_dir: Path,
    ) -> Tuple[Path, Path]:
        """Save OCR result to immutable raw JSON and Markdown files.

        Args:
            result: Result dictionary from parse_page.
            page_num: 1-indexed page number.
            json_dir: Target directory for raw JSON.
            md_dir: Target directory for raw Markdown.

        Returns:
            Tuple of (saved_json_path, saved_md_path).
        """
        json_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)

        filename_stem = f"page_{page_num:04d}"
        json_path = json_dir / f"{filename_stem}.json"
        md_path = md_dir / f"{filename_stem}.md"

        markdown_text = result.get("markdown", "")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        return json_path, md_path
