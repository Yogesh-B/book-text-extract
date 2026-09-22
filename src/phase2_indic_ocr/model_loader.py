import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from src.config import get_default_device, get_model_path
from src.utils.logger import get_logger

logger = get_logger("model_loader")


def ensure_model_in_sys_path(model_path: Path) -> None:
    """Ensure the model directory is in sys.path for importing indic_ocr."""
    model_str = str(model_path.resolve())
    if model_str not in sys.path:
        sys.path.insert(0, model_str)


def set_recognizer_batch_size(parser: Any, batch_size: int) -> None:
    """Configure internal crop batch_size on IndicOCR recognizer (HfRecognizer)."""
    configured = False
    try:
        if hasattr(parser, "recognizer"):
            rec = parser.recognizer
            if hasattr(rec, "backend") and hasattr(rec.backend, "batch_size"):
                rec.backend.batch_size = batch_size
                configured = True
                logger.info(f"Configured IndicOCR recognizer backend batch_size = {batch_size}")
            if hasattr(rec, "batch_size"):
                rec.batch_size = batch_size
                configured = True
    except Exception as e:
        logger.warning(f"Could not set recognizer batch_size directly: {e}")

    if not configured:
        logger.warning(
            "Unable to locate batch_size property on parser.recognizer.backend. "
            "Using model default."
        )


def load_indic_ocr(
    model_path: Optional[Path | str] = None,
    device: Optional[str] = None,
    compile_model: bool = False,
    crop_batch_size: Optional[int] = None,
):
    """Load IndicOCR model from local weights.

    Args:
        model_path: Custom path to indic-ocr directory. If None, uses default discovery.
        device: 'cuda' or 'cpu'. If None, detects best available device.
        compile_model: Whether to optimize recognizer with torch.compile.
        crop_batch_size: Crop batch size from CLI --crop-batch-size (mapped to recognizer batch_size).

    Returns:
        Loaded IndicOCR parser instance.
    """
    resolved_path = Path(model_path) if model_path else get_model_path()
    resolved_path = resolved_path.resolve()

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"IndicOCR model directory not found at: {resolved_path}. "
            "Please ensure weights are placed at ~/models/indic-ocr or set INDIC_OCR_MODEL_PATH."
        )

    ensure_model_in_sys_path(resolved_path)

    import torch
    from indic_ocr import IndicOCR

    target_device = device or get_default_device()
    if target_device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA requested or defaulted, but CUDA is unavailable. Falling back to CPU.")
        target_device = "cpu"

    logger.info(f"Loading IndicOCR model from: {resolved_path}")
    logger.info(f"Target compute device: {target_device}")
    if target_device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        vram_alloc = torch.cuda.memory_allocated(0) / (1024 * 1024)
        logger.info(f"GPU: {gpu_name} (Initial allocated VRAM: {vram_alloc:.1f} MB)")

    if target_device == "cuda":
        torch.backends.cudnn.benchmark = True
        logger.info("cuDNN benchmark mode enabled (auto-selects fastest convolution kernel).")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        logger.info("TF32 enabled for matmul and cuDNN (Tensor Core acceleration on Ampere+).")

    t0 = time.time()
    parser = IndicOCR.from_pretrained(resolved_path, device=target_device)
    load_time = time.time() - t0

    # Determine batch size: if not explicitly specified via CLI, auto-tune for small GPUs (<=4.5 GB)
    effective_crop_batch_size = crop_batch_size
    if effective_crop_batch_size is None and target_device == "cuda":
        total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        if total_vram_gb <= 4.5:
            effective_crop_batch_size = 2
            logger.info(
                f"Auto-detected {total_vram_gb:.2f} GB GPU VRAM (<= 4.5 GB). "
                f"Auto-tuning default crop batch_size = {effective_crop_batch_size} to prevent CUDA OOM."
            )

    if effective_crop_batch_size is not None:
        set_recognizer_batch_size(parser, effective_crop_batch_size)

    if compile_model:
        logger.info("Applying torch.compile(dynamic=True) to recognizer model...")
        tc0 = time.time()
        parser.recognizer.backend.model = torch.compile(
            parser.recognizer.backend.model,
            dynamic=True,
        )
        logger.info(
            f"torch.compile attached in {time.time() - tc0:.2f}s "
            "(graph tracing/optimization will complete during first page batch)."
        )

    logger.info(f"IndicOCR loaded successfully in {load_time:.2f}s on {target_device}.")
    return parser
