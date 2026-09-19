"""Page parsing and selection utilities."""
from typing import List, Set


def parse_page_selection(page_spec: str) -> List[int]:
    """Parse a flexible page selection string into a sorted list of unique 1-indexed page numbers.

    Supported formats:
    - Single page: "5" -> [5]
    - Range: "1-5" -> [1, 2, 3, 4, 5]
    - Comma-separated: "1,3,5" -> [1, 3, 5]
    - Mixed: "1-3, 7, 10-12" -> [1, 2, 3, 7, 10, 11, 12]
    - Whitespace tolerant: " 1 - 3 ,  7 " -> [1, 2, 3, 7]

    Raises:
        ValueError: If any part of the spec is invalid or page numbers are <= 0.
    """
    if not page_spec or not page_spec.strip():
        return []

    pages: Set[int] = set()
    parts = [p.strip() for p in page_spec.split(",") if p.strip()]

    for part in parts:
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2:
                raise ValueError(f"Invalid range expression: '{part}'")
            start_str, end_str = bounds[0].strip(), bounds[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise ValueError(f"Invalid range numbers in: '{part}'")
            start, end = int(start_str), int(end_str)
            if start < 1 or end < 1:
                raise ValueError(f"Page numbers must be >= 1, got '{part}'")
            if start > end:
                start, end = end, start  # auto-correct inverted range
            pages.update(range(start, end + 1))
        else:
            if not part.isdigit():
                raise ValueError(f"Invalid page number: '{part}'")
            p = int(part)
            if p < 1:
                raise ValueError(f"Page numbers must be >= 1, got {p}")
            pages.add(p)

    return sorted(list(pages))


def format_page_list(pages: List[int]) -> str:
    """Format a list of page numbers into a compact human-readable range string (e.g. '1-3, 5, 8-10')."""
    if not pages:
        return ""

    sorted_pages = sorted(list(set(pages)))
    ranges = []
    start = sorted_pages[0]
    prev = start

    for p in sorted_pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = p
            prev = p

    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")

    return ", ".join(ranges)
