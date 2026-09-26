# Scripts Reference

Complete reference for all pipeline scripts in the `scripts/` directory.

---

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [run_phase1.py — PDF → Images](#run_phase1py--pdf--images)
3. [run_phase2.py — Images → OCR Text](#run_phase2py--images--ocr-text)
4. [run_safe_batch.sh — End-to-End Batch Orchestrator](#run_safe_batchsh--end-to-end-batch-orchestrator)
5. [report_failures.py — Audit & Failure Report](#report_failurespy--audit--failure-report)
6. [retry_failed.py — Targeted Page Retry](#retry_failedpy--targeted-page-retry)
7. [reorder_blocks.py — Post-Processing Layout Inspector](#reorder_blockspy--post-processing-layout-inspector)
8. [run_phase3_verify.py — LLM Verification & Patch Generation](#run_phase3_verifypy--llm-verification--patch-generation)
9. [apply_patches.py — Patch Review & Application](#apply_patchespy--patch-review--application)
10. [Directory Layout](#directory-layout)
11. [Common Workflows](#common-workflows)

---

## Pipeline Overview

```
books/*.pdf
    |
    v  (Phase 1)
data/images/<book_slug>/page_NNNN.png
    |
    v  (Phase 2)
data/ocr_output/<book_slug>/
    +-- checkpoint.json              <- crash-recovery state
    +-- raw/                         <- IMMUTABLE; never overwritten
        +-- json/page_NNNN.json
        +-- markdown/page_NNNN.md
    |
    v  (Phase 3 — run_phase3_verify.py)
data/ocr_output/<book_slug>/patches/
    +-- page_NNNN.patch              <- standard unified diff per page
    +-- page_NNNN_diff.json          <- structured change log
    +-- book_full.patch              <- all pages combined
    +-- diff_summary.html            <- interactive visual audit report
    |
    v  (Phase 3.5 — apply_patches.py)
data/ocr_output/<book_slug>/verified/
    +-- markdown/page_NNNN.md        <- approved corrected text
```

The **safe batch script** drives Phase 1 -> Phase 2 for each book in a part file, cleans up intermediate images between books to stay within disk budget, and then automatically retries any failed pages.

---

## `run_phase1.py` — PDF → Images

**Purpose:** Rasterise Gujarati PDF pages to 300 DPI lossless PNG images and write a `manifest.json` alongside them. This is a pure CPU operation.

### Usage

```bash
# Single PDF
python scripts/run_phase1.py --input books/MyBook.pdf

# All PDFs in books/
python scripts/run_phase1.py --all

# Custom DPI and worker count
python scripts/run_phase1.py -i books/MyBook.pdf --dpi 300 --workers 8

# Only extract pages 1-20
python scripts/run_phase1.py -i books/MyBook.pdf --pages 1-20

# Smoke test: first 5 pages only
python scripts/run_phase1.py -i books/MyBook.pdf --max-pages 5

# Force re-render (overwrite existing images)
python scripts/run_phase1.py -i books/MyBook.pdf --force
```

### Arguments

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--input` | `-i` | `str` | — | Path to a single PDF (e.g. `books/MyBook.pdf`) |
| `--all` | — | flag | off | Process every `*.pdf` in `books/` |
| `--dpi` | — | `int` | `300` | Render resolution; higher = sharper but larger files |
| `--workers` | `-w` | `int` | `8` | Parallel page rendering processes |
| `--output-dir` | `-o` | `str` | `data/images/<slug>/` | Override default output directory |
| `--slug` | — | `str` | auto-detected | Override the book slug (only applies when processing a single PDF) |
| `--pages` | — | `str` | all pages | Page range: `'1-20'`, `'5'`, or `'5,12,40-45'` |
| `--max-pages` | — | `int` | unlimited | Cap on pages to extract (useful for smoke tests) |
| `--force` | `-f` | flag | off | Overwrite already-rendered images |

### Outputs

| Path | Description |
|------|-------------|
| `data/images/<book_slug>/page_NNNN.png` | Zero-padded PNG image for each page |
| `data/images/<book_slug>/manifest.json` | Metadata: total pages, DPI, extraction stats |

### Notes

- Requires only `PyMuPDF` (`fitz`); no GPU needed.
- Slugs are auto-generated from the PDF filename via `src.utils.slug.slugify_filename`. Known books have canonical slugs defined in `src/config.py:KNOWN_BOOK_SLUGS`.
- When `--all` is used, `--slug` is ignored (each book gets its own auto-slug).

---

## `run_phase2.py` — Images → OCR Text

**Purpose:** Run the `bodhan-ai/indic-ocr` model over page images produced by Phase 1, writing immutable raw JSON and Markdown outputs per page. Supports crash recovery via `checkpoint.json`.

### Usage

```bash
# Process a specific book (slug = folder name under data/images/)
python scripts/run_phase2.py --book Aadarsh_bhaktgatha

# Process all books found in data/images/
python scripts/run_phase2.py --all

# Point directly at an image directory
python scripts/run_phase2.py --images-dir /path/to/images

# Limit to a page range
python scripts/run_phase2.py -b MyBook --pages 10-50

# Smoke test: first 3 pages
python scripts/run_phase2.py -b MyBook --max-pages 3

# Retry only previously failed or incomplete pages
python scripts/run_phase2.py -b MyBook --retry-failed

# Use CPU (slower; useful when GPU VRAM is exhausted)
python scripts/run_phase2.py -b MyBook --device cpu

# Force overwrite of already-completed pages
python scripts/run_phase2.py -b MyBook --force

# Enable torch.compile for ~18% speed boost (requires warm-up on first run)
python scripts/run_phase2.py -b MyBook --compile

# Tune crop batch size to avoid CUDA OOM on dense pages
python scripts/run_phase2.py -b MyBook --crop-batch-size 8
```

### Arguments

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--book` | `-b` | `str` | — | Book slug (subdirectory name under `data/images/`) |
| `--images-dir` | `-i` | `str` | — | Direct path to page images directory (overrides `--book`) |
| `--all` | — | flag | off | Process all book directories in `data/images/` |
| `--pages` | — | `str` | all | Page range: `'1-20'`, `'50'`, or `'5,12,40-45'` |
| `--retry-failed` | — | flag | off | Only process pages that previously failed or have missing outputs |
| `--max-pages` | — | `int` | unlimited | Maximum pages to process (useful for smoke tests) |
| `--output-dir` | `-o` | `str` | `data/ocr_output/<slug>/` | Custom output root directory |
| `--model-path` | — | `str` | auto-located | Custom path to indic-ocr model weights |
| `--device` | — | `cuda`/`cpu` | auto | Explicit compute device |
| `--no-reorder` | — | flag | off | Disable column clustering and top-to-bottom block reordering |
| `--y-tolerance` | — | `float` | `20.0` | Vertical pixel tolerance for grouping same-line elements |
| `--compile` | — | flag | off | Enable `torch.compile(dynamic=True)` for ~18% faster inference |
| `--force` | `-f` | flag | off | Overwrite completed pages and re-run OCR |
| `--crop-batch-size` | — | `int` | auto | Text crop batch size sent to the recognizer. Auto: 2 on <=4.5 GB VRAM, 8 on larger GPUs. Set to 1-2 to prevent OOM on dense pages. |

### Outputs

| Path | Description |
|------|-------------|
| `data/ocr_output/<slug>/raw/json/page_NNNN.json` | Structured OCR result (blocks, bboxes, confidence) |
| `data/ocr_output/<slug>/raw/markdown/page_NNNN.md` | Reading-ordered Markdown text |
| `data/ocr_output/<slug>/checkpoint.json` | Progress tracker for resumable execution |

### Crash Recovery

All progress is continuously flushed to `checkpoint.json` after every page. If the process is interrupted, re-running the same command will automatically **skip completed pages** and continue from where it left off. Pages in the checkpoint's `failed_pages` list can be retried with `--retry-failed` or via `retry_failed.py`.

### VRAM & Memory Tips

- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` is set automatically by the script to reduce CUDA memory fragmentation on GPUs with <=4 GB VRAM.
- If you encounter CUDA OOM errors, lower `--crop-batch-size` to `2` or `1`, or fall back to `--device cpu`.
- `--compile` provides an ~18% inference speedup at the cost of a ~30-second warm-up on first invocation.

---

## `run_safe_batch.sh` — End-to-End Batch Orchestrator

**Purpose:** Orchestrate a complete Phase 1 -> Phase 2 pipeline for a list of books defined in a "part file". Designed for unattended overnight runs against a disk-constrained environment (e.g., a 30 GB disk budget). Intermediate images are deleted immediately after each book finishes OCR.

### Usage

```bash
# Basic usage - process all books listed in a part file
./scripts/run_safe_batch.sh temp/parts/part_1.txt

# Disable the automatic retry pass
AUTO_RETRY=0 ./scripts/run_safe_batch.sh temp/parts/part_1.txt
```

### Part File Format

A plain text file listing one PDF filename per line (relative to the `books/` directory). Lines starting with `#` and blank lines are ignored.

```
# Part 1 - Gujarati Religious Texts
Aadarsh bhaktgatha.pdf
Nari Ratno (SGVP).pdf
Bhakt Aakhyan.pdf
```

### Execution Flow

```
for each book in <PART_FILE>:
    1. Phase 1:  run_phase1.py -i books/<book>.pdf --workers 8
    2. Phase 2:  run_phase2.py -b <slug> --crop-batch-size 32
    3. Cleanup:  rm -rf data/images/<slug>/      <- frees disk immediately
    4. Report:   df -h /                         <- log disk usage

After all books:
    5. Failure report:  report_failures.py --part <PART_FILE>

If AUTO_RETRY=1 (default):
    6. Retry:         retry_failed.py --part <PART_FILE> --crop-batch-size 8
    7. Final report:  report_failures.py --part <PART_FILE>
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_RETRY` | `1` | Set to `0` to skip the automatic retry pass after the initial run |

### Error Handling

- **Phase 1 failure:** The book is skipped entirely (`continue`); subsequent books still run.
- **Phase 2 failure:** A warning is printed and the loop continues. Individual page errors are recorded in `checkpoint.json` and are not fatal to the batch.
- **Missing PDF:** A warning is printed and the book is skipped.

### Virtual Environment

The script automatically uses `.venv/bin/python` if a local virtual environment exists; otherwise falls back to the system `python3`.

---

## `report_failures.py` — Audit & Failure Report

**Purpose:** Inspect `checkpoint.json` files across books to audit OCR completion state. Prints a formatted summary table to the console and optionally writes a JSON report file.

### Usage

```bash
# Report on all books in data/ocr_output/
python scripts/report_failures.py

# Report on a specific book
python scripts/report_failures.py --book Aadarsh_bhaktgatha

# Report on all books from a part file
python scripts/report_failures.py --part temp/parts/part_1.txt

# Custom JSON report output path
python scripts/report_failures.py --output my_report.json
```

### Arguments

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--book` | `-b` | `str` | — | Single book slug to inspect |
| `--part` | `-p` | `str` | — | Part file path; reports on all books listed in it |
| `--output` | `-o` | `str` | `data/ocr_output/failure_report.json` | Destination for the JSON summary |

### Output Format

```
================================================================================
                    INDICOCR EXECUTION & FAILURE REPORT
================================================================================
Book Slug                           | Total  | Done   | Fail   | Miss   | Status
---
Aadarsh_bhaktgatha                  | 312    | 310    | 1      | 1      | in_progress
Nari_Ratno_SGVP                     | 198    | 198    | 0      | 0      | completed
================================================================================
Summary: 2 book(s) audited. 1 book(s) have incomplete/failed pages (2 total pages).

--- DETAILED FAILURE & MISSING BREAKDOWN ---
* Book: Aadarsh_bhaktgatha
  Failed Pages:
    - Page 0042: CUDA out of memory. Tried to allocate...
  Summary Range of Failed Pages: 42
  Missing Pages (not in checkpoint/output): 87
================================================================================
```

### Column Definitions

| Column | Description |
|--------|-------------|
| `Total` | Total page count from `checkpoint.json` |
| `Done` | Pages with verified non-empty `.json` **and** `.md` output files on disk |
| `Fail` | Pages recorded in `checkpoint.json:failed_pages` |
| `Miss` | Pages expected but absent from both the checkpoint and output directories |
| `Status` | `checkpoint.json:status` field (`in_progress` / `completed` / `not_started`) |

> **Note:** `Done` is verified against actual files on disk, not just the checkpoint's `completed_pages` list. A page is only counted as Done if both `page_NNNN.json` and `page_NNNN.md` exist and are non-empty.

---

## `retry_failed.py` — Targeted Page Retry

**Purpose:** Re-run OCR on only the pages that previously failed or are missing from a book's checkpoint. It re-extracts only those specific pages from the source PDF (avoiding a full Phase 1 re-run), processes them with a smaller, safer `--crop-batch-size`, and cleans up the temporary images afterwards.

### Usage

```bash
# Retry all failed pages for a single book
python scripts/retry_failed.py --book Aadarsh_bhaktgatha

# Retry with an explicit PDF path (if auto-location fails)
python scripts/retry_failed.py --book Aadarsh_bhaktgatha --pdf "books/Aadarsh bhaktgatha.pdf"

# Retry all failed books from a part file
python scripts/retry_failed.py --part temp/parts/part_1.txt

# Retry all books in data/ocr_output/ that have failures
python scripts/retry_failed.py --all

# Retry specific page numbers only
python scripts/retry_failed.py --book Aadarsh_bhaktgatha --pages 42,87,120-125

# Use a smaller batch size to reduce VRAM pressure
python scripts/retry_failed.py --book Aadarsh_bhaktgatha --crop-batch-size 2

# Keep extracted images after processing (for debugging)
python scripts/retry_failed.py --book Aadarsh_bhaktgatha --keep-images

# Fall back to CPU
python scripts/retry_failed.py --book Aadarsh_bhaktgatha --device cpu
```

### Arguments

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--book` | `-b` | `str` | — | Book slug to retry |
| `--pdf` | — | `str` | auto-located | Direct path to the source PDF (if slug lookup fails) |
| `--part` | `-p` | `str` | — | Part file; retries all failed books listed in it |
| `--all` | — | flag | off | Retry every book in `data/ocr_output/` that has failures |
| `--pages` | — | `str` | auto from checkpoint | Explicit page numbers to retry: `'5,12,42-45'` |
| `--crop-batch-size` | — | `int` | `8` | Batch size for recognizer inference (smaller = safer on VRAM) |
| `--device` | — | `cuda`/`cpu` | auto | Explicit compute device |
| `--keep-images` | — | flag | off | Retain extracted page images after processing |
| `--workers` | — | `int` | `4` | Parallel workers for Phase 1 image extraction |

### How It Works

1. **Inspect checkpoint** — reads `checkpoint.json` to identify `failed_pages` and `missing_pages`.
2. **Extract targeted pages** — calls `PDFImageExtractor` with `force=True` for only those page numbers (not the whole book).
3. **Run Phase 2 OCR** — processes only those images with a smaller, safer crop batch size. `force=True` overwrites any stale state for those pages.
4. **Clean up** — deletes the temporary images directory unless `--keep-images` is set.
5. **Shared engine** — when retrying multiple books in a single invocation, the IndicOCR engine is loaded once and reused across all books to avoid repeated warm-up overhead.

> **Tip:** After `retry_failed.py` finishes, run `report_failures.py` to confirm all pages are now complete.

---

## `reorder_blocks.py` — Post-Processing Layout Inspector

**Purpose:** A developer/debugging utility that takes a raw `page_NNNN.json` OCR output and applies two-phase layout detection and top-to-bottom reordering. Useful for inspecting the column-detection logic in isolation without re-running OCR.

### Usage

```bash
# Reorder the default test page (data/test_output/page_0022.json)
python scripts/reorder_blocks.py

# Pass a custom JSON path as a positional argument
python scripts/reorder_blocks.py data/ocr_output/MyBook/raw/json/page_0042.json
```

### Outputs

Given `page_NNNN.json`, the script writes two files alongside it:

| Output | Description |
|--------|-------------|
| `page_NNNN_reordered.json` | JSON with blocks sorted in reading order and `order` indices added |
| `page_NNNN_reordered.md` | Clean Markdown from the reordered blocks |

It also prints a reading-order comparison table to stdout:

```
===========================================================================
READING ORDER COMPARISON - page_0042.json
Page width: 3000px  |  Detected main blocks: 2
===========================================================================
New#  Old#     Y-Top  Side    Snippet
---------------------------------------------------------------------------
0     3          42.0 Left    ભગવાન શ્રી સ્વામિ...
1     0         110.5 Left    અહો ! ધન્ય છે...
2     5         210.0 Right   ...
===========================================================================
```

### Notes

- Loads `src/phase2_indic_ocr/reorder.py` directly without importing the full package, so it does **not** require PyTorch or CUDA.
- In normal pipeline usage, reordering is applied automatically by `run_phase2.py` (controlled by `--no-reorder` and `--y-tolerance`).

---

## `run_phase3_verify.py` — LLM Verification & Patch Generation

**Purpose:** Send raw OCR markdown pages through the local Gemma 4 model (via `llama-server` OpenAI-compatible API) to detect OCR defects. Produces per-page unified diff `.patch` files, structured JSON change logs, and an interactive HTML audit report. **Raw OCR files are never modified.**

> **Prerequisite:** `llama-server` must be running on port 8080 before invoking this script.
> ```bash
> llama-server -m ~/models/gemma-4-E2B-it-qat-GGUF/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf --port 8080
> ```

### Usage

```bash
# Process all pages of a book
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha

# Specify server URL and model name explicitly
python scripts/run_phase3_verify.py \
  --book-slug Aadarsh_bhaktgatha \
  --server-url http://127.0.0.1:8080/v1 \
  --model-name gemma-4-e2b

# Smoke test: first 5 pages only
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha --pages 1-5

# Single page
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha --pages 14

# Re-process pages that already have patches (overwrite)
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha --force

# Skip generating the HTML report
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha --no-report

# Increase timeout for slow hardware
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha --timeout 300
```

### Arguments

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--book-slug` | `str` | **required** | Book slug (subdirectory name under `data/ocr_output/`) |
| `--server-url` | `str` | `http://127.0.0.1:8080/v1` | Base URL of the llama-server OpenAI-compatible API |
| `--model-name` | `str` | `gemma-4-e2b` | Model ID passed in API requests |
| `--pages` | `str` | all pages | Page range: `'1-10'`, `'5'`. Omit to process all pages. |
| `--timeout` | `float` | `180` | Per-request timeout in seconds |
| `--max-tokens` | `int` | `4096` | Maximum tokens for the LLM response |
| `--force` | flag | off | Re-process pages that already have patch files |
| `--no-report` | flag | off | Skip generating `diff_summary.html` |

### Outputs

| Path | Description |
|------|-------------|
| `data/ocr_output/<slug>/patches/page_NNNN.patch` | Standard unified diff (empty if no changes found) |
| `data/ocr_output/<slug>/patches/page_NNNN_diff.json` | Structured change log: `{line, type, original, proposed, reason}` |
| `data/ocr_output/<slug>/patches/book_full.patch` | All per-page patches concatenated |
| `data/ocr_output/<slug>/patches/diff_summary.html` | Dark-theme interactive HTML report with filter buttons |

### Change Types

| Type | Description |
|------|-------------|
| `punctuation_clean` | Stray leading `?`, `|`, `।` from paper smudges or borders |
| `space_fix` | Accidental space splitting a single Gujarati word |
| `conjunct_fix` | Broken ligature / conjunct (e.g., `ભ ક ત` → `ભક્ત`) |
| `spelling_fix` | Misread matra or character substitution |
| `insert` / `remove` | Line-level additions or deletions |

### Resume Behaviour

Pages that already have both a `.patch` and `_diff.json` file are skipped automatically. Use `--force` to override.

---

## `apply_patches.py` — Patch Review & Application

**Purpose:** Review the LLM-proposed changes and selectively apply them into `verified/markdown/`. Supports three modes: interactive hunk-by-hunk prompting, batch auto-accept, and dry-run preview. **Raw OCR files are never modified.**

### Usage

```bash
# Interactive mode (default) — prompted per change
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha

# Dry-run — preview all proposed changes without writing anything
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --dry-run

# Batch: auto-accept only safe low-risk types (punctuation + space)
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha \
  --batch --accept-types punctuation_clean space_fix

# Batch: auto-accept all change types
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --batch --all

# Process a specific page range
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --pages 1-10

# Single page, interactive
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --pages 14
```

### Arguments

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--book-slug` | `str` | **required** | Book slug (subdirectory name under `data/ocr_output/`) |
| `--pages` | `str` | all pages | Page range: `'1-10'`, `'5'`. Omit to process all pages. |
| `--interactive` | flag | **default** | Prompt `[y/n/a/q]` for each proposed change |
| `--batch` | flag | off | Auto-accept without prompting (mutually exclusive with `--interactive`) |
| `--dry-run` | flag | off | Preview only — no files written (mutually exclusive with `--interactive`) |
| `--accept-types` | `str…` | `punctuation_clean space_fix` | With `--batch`: only accept changes of these types |
| `--all` | flag | off | With `--batch`: accept all change types regardless of type |

### Interactive Prompt

```
══════════════════════════════════════════════════════════════
[Page 14] – 2 proposed change(s)

  [1/2] Line   8 [punctuation_clean]
    - '? દૂધપાક કરે પણ અંદર સાકર ન નાખે તો'
    + 'દૂધપાક કરે પણ અંદર સાકર ન નાખે તો'
    ℹ  OCR correction (punctuation_clean)
  Apply? [y]es / [n]o / [a]ll remaining / [q]uit >
```

### Outputs

| Path | Description |
|------|-------------|
| `data/ocr_output/<slug>/verified/markdown/page_NNNN.md` | Corrected text with accepted changes applied |

Pages with zero proposed changes are copied from raw to verified unchanged.

---

## Directory Layout

```
text-extract/
+-- books/                        <- Source Gujarati PDFs
+-- data/
|   +-- images/
|   |   +-- <book_slug>/          <- Phase 1 output (deleted after Phase 2)
|   |       +-- manifest.json
|   |       +-- page_NNNN.png
|   +-- ocr_output/
|       +-- <book_slug>/
|           +-- checkpoint.json   <- Phase 2 crash-recovery state
|           +-- raw/              <- IMMUTABLE Phase 2 output
|           |   +-- json/page_NNNN.json
|           |   +-- markdown/page_NNNN.md
|           +-- patches/          <- Phase 3 output
|           |   +-- page_NNNN.patch
|           |   +-- page_NNNN_diff.json
|           |   +-- book_full.patch
|           |   +-- diff_summary.html
|           +-- verified/         <- Phase 3.5 output (human-approved)
|               +-- markdown/page_NNNN.md
+-- temp/
|   +-- parts/
|       +-- part_N.txt            <- Book lists for batch runs
+-- scripts/
    +-- run_phase1.py
    +-- run_phase2.py
    +-- run_safe_batch.sh
    +-- report_failures.py
    +-- retry_failed.py
    +-- reorder_blocks.py
    +-- run_phase3_verify.py      <- Phase 3: LLM verification
    +-- apply_patches.py          <- Phase 3.5: patch review & apply
```

---

## Common Workflows

### Full batch run (recommended)

```bash
# 1. Create a part file listing your PDFs
cat > temp/parts/part_1.txt << 'EOF'
Aadarsh bhaktgatha.pdf
Nari Ratno (SGVP).pdf
EOF

# 2. Run the safe batch script (handles everything end-to-end)
./scripts/run_safe_batch.sh temp/parts/part_1.txt
```

### Smoke test a single book

```bash
# Phase 1: extract first 5 pages
python scripts/run_phase1.py -i books/MyBook.pdf --max-pages 5

# Phase 2: OCR those 5 pages
python scripts/run_phase2.py --book MyBook --max-pages 5
```

### Resume an interrupted run

```bash
# Phase 2 automatically skips already-completed pages
python scripts/run_phase2.py --book Aadarsh_bhaktgatha
```

### Check what failed

```bash
python scripts/report_failures.py --book Aadarsh_bhaktgatha
```

### Retry only failed pages

```bash
# Single book
python scripts/retry_failed.py --book Aadarsh_bhaktgatha

# Entire part file
python scripts/retry_failed.py --part temp/parts/part_1.txt
```

### Run on CPU (no GPU available)

```bash
python scripts/run_phase2.py --book MyBook --device cpu
```

### Debug column detection on a single page

```bash
python scripts/reorder_blocks.py data/ocr_output/MyBook/raw/json/page_0042.json
```

### Run Phase 3 LLM verification (requires llama-server on port 8080)

```bash
# Smoke test: verify first 5 pages
python scripts/run_phase3_verify.py \
  --book-slug Aadarsh_bhaktgatha \
  --pages 1-5

# Full book
python scripts/run_phase3_verify.py --book-slug Aadarsh_bhaktgatha

# Open the HTML report to audit results
xdg-open data/ocr_output/Aadarsh_bhaktgatha/patches/diff_summary.html
```

### Review and apply patches (Phase 3.5)

```bash
# Interactive: decide hunk-by-hunk
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha

# Dry-run first to preview without touching files
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --dry-run

# Batch: auto-apply only safe punctuation/space fixes
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha \
  --batch --accept-types punctuation_clean space_fix

# Batch: accept every proposed change
python scripts/apply_patches.py --book-slug Aadarsh_bhaktgatha --batch --all
```

### Using standard Unix patch tooling

Because patches are standard unified diffs, you can also use native tools:

```bash
# Dry-run inspection
patch --dry-run -p1 -d data/ocr_output/Aadarsh_bhaktgatha/ \
  < data/ocr_output/Aadarsh_bhaktgatha/patches/book_full.patch

# Apply all accepted patches
patch -p1 -d data/ocr_output/Aadarsh_bhaktgatha/ \
  < data/ocr_output/Aadarsh_bhaktgatha/patches/book_full.patch
```
