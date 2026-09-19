#!/usr/bin/env bash
set -e

PART_FILE=$1

if [ -z "$PART_FILE" ]; then
    echo "Usage: ./scripts/run_safe_batch.sh temp/parts/part_1.txt"
    exit 1
fi

echo "=============================================="
echo "Starting Safe Batch OCR for: $PART_FILE"
echo "=============================================="

# Prefer local virtualenv python if available
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

# Ensure output directories exist
mkdir -p data/images data/ocr_output

while IFS= read -r book_pdf || [ -n "$book_pdf" ]; do
    # Skip empty lines or comments
    [[ -z "$book_pdf" || "$book_pdf" =~ ^#.* ]] && continue

    pdf_path="books/$book_pdf"

    if [ ! -f "$pdf_path" ]; then
        echo "[WARNING] File not found: $pdf_path, skipping..."
        continue
    fi

    echo "----------------------------------------------"
    echo "Processing: $book_pdf"
    echo "----------------------------------------------"

    # 1. Run Phase 1 (PDF -> Images)
    if ! "$PYTHON_BIN" scripts/run_phase1.py -i "$pdf_path" --workers 8; then
        echo "[ERROR] Phase 1 image extraction failed for $book_pdf"
        continue
    fi

    # Derive slug name (or find newly created folder in data/images)
    book_slug=$("$PYTHON_BIN" -c "from src.utils.slug import slugify_filename; from pathlib import Path; print(slugify_filename(Path('$pdf_path').name))")

    # 2. Run Phase 2 (Images -> Markdown & JSON with 24GB VRAM batch size)
    # Don't abort entire part if a few pages fail; errors are recorded in checkpoint.json
    "$PYTHON_BIN" scripts/run_phase2.py -b "$book_slug" --crop-batch-size 32 || {
        echo "[WARNING] Phase 2 encountered page issues for $book_slug. Check checkpoint.json."
    }

    # 3. CRITICAL: Clean up images immediately to stay under 30GB disk limit
    echo "[CLEANUP] Removing intermediate images for: $book_slug"
    rm -rf "data/images/$book_slug"

    # 4. Check available disk space
    df -h / | awk 'NR==2 {print "Disk Available: "$4" / "$2" ("$5" used)"}'

done < "$PART_FILE"

echo "=============================================="
echo "Part initial pass completed. Generating Failure Report..."
echo "=============================================="
"$PYTHON_BIN" scripts/report_failures.py --part "$PART_FILE"

# Optional automatic retry pass for failed pages with smaller batch size (8)
if [ "${AUTO_RETRY:-1}" = "1" ]; then
    echo "=============================================="
    echo "Running Automatic Targeted Retry (batch size 8)..."
    echo "=============================================="
    "$PYTHON_BIN" scripts/retry_failed.py --part "$PART_FILE" --crop-batch-size 8

    echo "=============================================="
    echo "Final Failure Report After Retry:"
    echo "=============================================="
    "$PYTHON_BIN" scripts/report_failures.py --part "$PART_FILE"
fi

echo "=============================================="
echo "Batch workflow completed!"
echo "=============================================="
