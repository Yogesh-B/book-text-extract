import os
import re
import unicodedata
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = PROJECT_ROOT / "books"
DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"
OCR_OUTPUT_DIR = DATA_DIR / "ocr_output"
DIST_DIR = PROJECT_ROOT / "dist"
MODELS_DIR = PROJECT_ROOT / "models"

# Phase 1 Extraction Defaults
DEFAULT_DPI = 300
DEFAULT_IMAGE_FORMAT = "png"
DEFAULT_WORKERS = 8

# Canonical slugs for known books
KNOWN_BOOK_SLUGS = {
    "Aadarsh bhaktgatha.pdf": "Aadarsh_bhaktgatha",
    "Nari Ratno (SGVP).pdf": "Nari_Ratno_SGVP",
    "આદર્શ ભક્તગાથા, હરિયાળા.pdf": "Aadarsh_bhaktgatha_Hariyala",
    "ભક્ત આખ્યાન.pdf": "Bhakt_Aakhyan",
    "ભક્ત કલ્પતરૂ 1 (વંથલિ ગુરુકુલ).pdf": "Bhakt_Kalpataru_1_Vanthali_Gurukul",
}


def _is_slug_char(ch: str) -> bool:
    """Check if a character should be preserved in a book slug.

    Keeps word characters (letters, digits, underscore) AND Unicode
    combining marks (category M) which include Indic viramas, matras,
    and other dependent vowel/consonant signs essential for readable
    Gujarati text.
    """
    if ch == "_":
        return True
    cat = unicodedata.category(ch)
    # L = Letter, N = Number, M = Mark (virama, matras, etc.)
    return cat[0] in ("L", "N", "M")


def get_book_slug(pdf_path: str | Path) -> str:
    """Return a clean directory slug for a PDF filename."""
    name = Path(pdf_path).name
    if name in KNOWN_BOOK_SLUGS:
        return KNOWN_BOOK_SLUGS[name]

    # Clean up name: remove .pdf extension
    stem = Path(pdf_path).stem
    # Replace characters that are not letters, digits, marks, or underscores.
    # Unlike the bare \w regex, this preserves Unicode combining marks (category M)
    # so Gujarati conjuncts (e.g. શ્રી) stay intact instead of becoming શ_ર.
    slug = "".join(ch if _is_slug_char(ch) else "_" for ch in stem)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "unnamed_book"


def get_model_path() -> Path:
    """Find the IndicOCR model directory."""
    env_path = os.environ.get("INDIC_OCR_MODEL_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    workspace_path = MODELS_DIR / "indic-ocr"
    if workspace_path.exists():
        return workspace_path
    home_path = Path.home() / "models" / "indic-ocr"
    if home_path.exists():
        return home_path
    return home_path


def get_default_device() -> str:
    """Determine best available compute device for OCR."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    except ImportError:
        return "cpu"


def get_ocr_raw_dir(book_slug: str) -> Path:
    """Path to immutable raw OCR output directory for a book."""
    return OCR_OUTPUT_DIR / book_slug / "raw"


def get_ocr_raw_json_dir(book_slug: str) -> Path:
    """Path to raw JSON output directory for a book."""
    return get_ocr_raw_dir(book_slug) / "json"


def get_ocr_raw_md_dir(book_slug: str) -> Path:
    """Path to raw Markdown output directory for a book."""
    return get_ocr_raw_dir(book_slug) / "markdown"


def get_ocr_checkpoint_file(book_slug: str) -> Path:
    """Path to checkpoint JSON file for a book."""
    return OCR_OUTPUT_DIR / book_slug / "checkpoint.json"

