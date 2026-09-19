# Failure Reporting & Targeted Retry Walkthrough

This document outlines the architecture, usage, and workflows for reporting failed OCR pages and retrying **only those specific failed pages** with smaller batch sizes.

---

## 1. Problem Context & Overview

In high-throughput OCR batches (`run_safe_batch.sh`), books are converted into 300 DPI PNG images (`data/images/<book_slug>/`), processed through the IndicOCR model, and the intermediate images are immediately deleted to respect strict disk quotas (< 30GB).

Occasionally, dense pages (e.g. multi-column layouts, tables, or complex Gujarati scripts) can cause **GPU CUDA Out of Memory (OOM)** errors when using aggressive batch sizes (such as `--crop-batch-size 32`).

### Goals of the Solution
1. **Never kill the entire batch**: When individual pages fail, log them cleanly in the book's `checkpoint.json` and proceed with the remaining pages and books.
2. **Selective image rendering**: Extract **only** the failed pages from the original PDF into images (takes < 1 second and consumes virtually no disk space).
3. **Targeted automatic / manual retry**: Re-run OCR only on those failed pages using a smaller, safer batch size (e.g. `--crop-batch-size 8` or CPU fallback).
4. **Comprehensive failure reporting**: Produce clear summary tables and JSON reports of failed and missing pages.

---

## 2. Tools & Scripts

### A. Failure Reporting CLI (`scripts/report_failures.py`)
Scans `data/ocr_output/*/checkpoint.json` across all processed books or a specific part file to check completion status, failed pages with exact error messages (e.g. CUDA OOM), and missing output files.

```bash
# Report status across all processed books:
.venv/bin/python scripts/report_failures.py

# Report status for a specific part file:
.venv/bin/python scripts/report_failures.py --part temp/parts/part_1.txt

# Report status for an individual book:
.venv/bin/python scripts/report_failures.py --book 72181_Shri_Harikrushna_Charitramrut_Sagar_Bhag_1
```

**Example Output:**
```
================================================================================
                    INDICOCR EXECUTION & FAILURE REPORT                    
================================================================================
Book Slug                           | Total  | Done   | Fail   | Miss   | Status      
--------------------------------------------------------------------------------------
72181_Shri_Harikrushna_Charitramrut | 495    | 113    | 3      | 379    | in_progress 
================================================================================
Summary: 1 book(s) audited. 1 book(s) have incomplete/failed pages (382 total pages).

--- DETAILED FAILURE & MISSING BREAKDOWN ---

* Book: 72181_Shri_Harikrushna_Charitramrut_Sagar_Bhag_1
  Failed Pages:
    - Page 0077: CUDA out of memory. Tried to allocate 82.00 MiB.
    - Page 0083: CUDA out of memory. Tried to allocate 82.00 MiB.
    - Page 0091: CUDA out of memory. Tried to allocate 86.00 MiB.
  Summary Range of Failed Pages: 77, 83, 91
```

---

### B. Targeted Retry CLI (`scripts/retry_failed.py`)
Automates the full recovery loop:
1. Identifies failed pages from `checkpoint.json` (or accepts manual `--pages`).
2. Locates the source PDF in `books/`.
3. Calls Phase 1 to render **only** those specific page images into `data/images/<book_slug>/`.
4. Runs Phase 2 OCR on those pages with a safer `--crop-batch-size` (default: 8).
5. Updates `checkpoint.json` and output files (`raw/json/` and `raw/markdown/`).
6. Cleans up the temporary images.

```bash
# Auto-retry all failed pages in a part file with batch size 8:
.venv/bin/python scripts/retry_failed.py --part temp/parts/part_1.txt --crop-batch-size 8

# Auto-retry all failed pages for a single book:
.venv/bin/python scripts/retry_failed.py --book 72181_Shri_Harikrushna_Charitramrut_Sagar_Bhag_1 --crop-batch-size 8

# Manually retry explicit pages with an extra-safe batch size (or on CPU):
.venv/bin/python scripts/retry_failed.py --book <slug> --pages 77,83,91 --crop-batch-size 4
.venv/bin/python scripts/retry_failed.py --book <slug> --pages 77 --device cpu
```

---

### C. Enhanced Phase 1 & Phase 2 Scripts

#### `scripts/run_phase1.py`
Supports flexible arbitrary page selections via `--pages`:
```bash
# Extract only pages 77, 83, and 91:
.venv/bin/python scripts/run_phase1.py -i "books/72181_Shri-Harikrushna-Charitramrut-Sagar-Bhag-1.pdf" --pages 77,83,91
```

#### `scripts/run_phase2.py`
Supports flexible page selection and automatic retry:
```bash
# Process only specific pages:
.venv/bin/python scripts/run_phase2.py -b <book_slug> --pages 77,83,91 --crop-batch-size 8

# Automatically retry all failed pages in checkpoint:
.venv/bin/python scripts/run_phase2.py -b <book_slug> --retry-failed --crop-batch-size 8
```

---

### D. Safe Batch Runner Integration (`scripts/run_safe_batch.sh`)
The batch script now includes error resilience and an automatic retry phase:

```bash
./scripts/run_safe_batch.sh temp/parts/part_1.txt
```

**Lifecycle per Part:**
1. Loops through each book in the part file:
   - Phase 1 (PDF -> Images)
   - Phase 2 (Images -> Markdown & JSON with crop batch size 32)
   - Deletes intermediate images immediately
   - Does not abort if a book has page failures
2. Runs `report_failures.py` to print a comprehensive failure table.
3. Automatically launches `retry_failed.py` with `--crop-batch-size 8` to resolve failed pages.
4. Generates a final post-retry report.

*(To disable automatic retry at the end of the batch run, set `AUTO_RETRY=0 ./scripts/run_safe_batch.sh ...`)*

---

## 3. Python Utility Modules

- **[`src/utils/pages.py`](file:///home/yogesh/test/text-extract/src/utils/pages.py)**:
  - `parse_page_selection(spec: str) -> List[int]`: Converts `"1-3, 7, 10-12"` to `[1, 2, 3, 7, 10, 11, 12]`.
  - `format_page_list(pages: List[int]) -> str`: Converts `[1, 2, 3, 7, 10, 11, 12]` to `"1-3, 7, 10-12"`.
- **[`src/phase1_pdf_to_images/extractor.py`](file:///home/yogesh/test/text-extract/src/phase1_pdf_to_images/extractor.py)**:
  - Added `page_numbers: Optional[List[int]]` parameter to `PDFImageExtractor.extract()`.
