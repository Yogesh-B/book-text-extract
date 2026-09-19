"""Slug utility module."""
from pathlib import Path
from src.config import get_book_slug


def slugify_filename(pdf_path: str | Path) -> str:
    """Return canonical slug for a given PDF path or filename."""
    return get_book_slug(pdf_path)
