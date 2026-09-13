import re
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

def get_book_slug(pdf_path: str | Path) -> str:
    """Return a clean directory slug for a PDF filename."""
    name = Path(pdf_path).name
    if name in KNOWN_BOOK_SLUGS:
        return KNOWN_BOOK_SLUGS[name]

    # Clean up name: remove .pdf extension
    stem = Path(pdf_path).stem
    # Replace non-word characters (spaces, punctuation, brackets) with underscore
    slug = re.sub(r"[^\w]+", "_", stem, flags=re.UNICODE).strip("_")
    return slug or "unnamed_book"
