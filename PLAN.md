# IndicOCR Gujarati PDF Text Extraction Pipeline: Complete Implementation Plan

## 1. Executive Overview

Many legacy Gujarati religious and cultural literature PDFs suffer from two major text-searchability issues:
1. **Legacy Non-Unicode 8-bit Font Encoding** (e.g., `Nari Ratno (SGVP).pdf`): Text is selectable in PDF viewers, but extracting or searching yields raw ASCII character codes (`nkuÞ Œku ? þheh nkuÞ ...`) instead of UTF-8 Gujarati glyphs.
2. **Scanned Hardcopy Books** (e.g., `Aadarsh bhaktgatha.pdf`): High-resolution physical scans with dual-column layouts, aging artifacts, skew, and bleed-through, containing no underlying text layer.

Even with state-of-the-art OCR (`bodhan-ai/indic-ocr` at ~91.7% word accuracy), real-world scanned pages produce subtle OCR errors: misplaced matras (હ્રસ્વ/દીર્ઘ), broken conjuncts (જોડાક્ષર), hyphenated line splits, and speckle noise.

### Critical Principle: Zero Silent Overwrites
Religious and historical texts require complete fidelity. **The verification step MUST NOT automatically or silently mutate the extracted text.**
Instead, the verification step functions as an auditor that produces **standard patch / diff files** (`.patch`, `.diff`, and structured JSON change logs) alongside a visual review report. The user maintains complete control to:
- Inspect every proposed modification.
- Manually apply or reject hunks using standard Unix `patch`.
- Interactively accept/reject changes via an inspection script.
- Optionally run a second scripted or LLM verification pass before any change is finalized.

---

## 2. Pipeline Architecture

```
+------------------------------------------------------+
|                 Source Gujarati PDFs                 |
|             (/books/*.pdf - ~100MB each)             |
+------------------------------------------------------+
                           |
                           v
+======================================================+
| PHASE 1: PDF to High-Resolution Image Extraction     |
| - Fast rasterization using PyMuPDF (fitz)            |
| - Configurable DPI (default 300 DPI for high OCR acc)|
| - Multiprocessing page extraction with manifest.json |
+======================================================+
                           |
                           v Output: Intermediate Page Images
                           | (data/images/<book>/page_0001.png)
                           |
+======================================================+
| PHASE 2: IndicOCR Document Parsing & Transcription   |
| - Model: bodhan-ai/indic-ocr (Bodhan AI / AI4Bharat) |
|   * Stage A: IndicDocLayout (PP-DocLayoutV3/RT-DETR) |
|     Detects 37 classes, columns & reading order      |
|   * Stage B: IndicBlockOCR (Qwen3.5-0.8B + Sarvam-30B|
|     Transcribes visual crops into clean UTF-8 Gujarati
| - Checkpoint manager for crash recovery & resume     |
+======================================================+
                           |
                           v Output: Raw Immutable OCR Text
                           | (data/ocr_output/<book>/raw/)
                           |
+======================================================+
| PHASE 3: Local LLM Verification & Patch Generation   |
| - Local Engine: llama-server (OpenAI API) or llama-cli
| - Model: Gemma 4 E2B (local GGUF, offline, zero-cost)|
| - Compares raw OCR against grammatical/lexical rules |
| - Outputs standard unified diffs (.patch), word-level|
|   JSON change logs, and an interactive HTML report   |
| - NO SILENT OVERWRITES: Raw OCR remains untouched!   |
+======================================================+
                           |
                           v Output: Review Patches & Diffs
                           | (data/ocr_output/<book>/patches/)
                           |
+======================================================+
| PHASE 3.5: Patch Review & Application (Human-in-Loop)|
| - Method A: Standard Unix `patch -p1 < book.patch`   |
| - Method B: Interactive CLI (`apply_patches.py -i`)  |
|             Prompt: [y/n/all/quit] per change hunk   |
| - Method C: Secondary LLM / scripted rule filter     |
| - Method D: Batch apply after visual HTML diff audit |
+======================================================+
                           |
                           v Output: Approved Verified Text
                           | (data/ocr_output/<book>/verified/)
                           |
+======================================================+
| PHASE 4: Delivery & Searchable Artifact Generation   |
| 1. Searchable "Sandwich" PDF (injected Unicode layer)|
| 2. Consolidated Book Markdown (E-reader / Web ready) |
| 3. SQLite Full-Text Search Index (FTS5 for apps)     |
+======================================================+
```

---

## 3. Project Directory Structure

```text
text-extract/
├── books/                             # Input PDF documents
│   ├── Aadarsh bhaktgatha.pdf
│   ├── Nari Ratno (SGVP).pdf
│   └── ...
├── data/
│   ├── images/                        # Phase 1 output (intermediate page images)
│   │   ├── Nari_Ratno_SGVP/
│   │   │   ├── manifest.json          # Page dimensions, DPI, total pages
│   │   │   ├── page_0001.png
│   │   │   └── ...
│   │   └── Aadarsh_bhaktgatha/
│   │       ├── manifest.json
│   │       ├── page_0001.png
│   │       └── ...
│   └── ocr_output/                    # OCR, Patches, and Verified outputs
│       ├── Nari_Ratno_SGVP/
│       │   ├── checkpoint.json        # Progress state for resume capability
│       │   ├── raw/                   # Immutable raw output from Phase 2
│       │   │   ├── json/page_0001.json
│       │   │   └── markdown/page_0001.md
│       │   ├── patches/               # Generated diffs & patches from Phase 3
│       │   │   ├── page_0001.patch    # Standard unified diff for page 1
│       │   │   ├── page_0001_diff.json# Word-level changes: {line, original, proposed, reason}
│       │   │   ├── book_full.patch    # Combined patch for the entire book
│       │   │   └── diff_summary.html  # Color-coded visual audit report (red/green)
│       │   ├── verified/              # Created ONLY when user applies patches
│       │   │   ├── json/page_0001.json
│       │   │   ├── markdown/page_0001.md
│       │   │   └── Nari_Ratno_SGVP_final.md
│       │   └── ...
│       └── ...
├── dist/                              # Phase 4 output (searchable deliverables)
│   ├── searchable_pdfs/               # Injected invisible text layer PDFs
│   └── search_indexes/                # SQLite FTS databases for app integration
├── models/                            # Local weights (IndicOCR snapshot, Gemma GGUF)
├── src/
│   ├── __init__.py
│   ├── config.py                      # Global configs, paths, DPI, LLM settings
│   ├── phase1_pdf_to_images/          # Phase 1: PDF to Image conversion
│   │   ├── __init__.py
│   │   ├── extractor.py               # PyMuPDF rasterizer with multiprocessing
│   │   └── preprocessor.py            # Contrast adjustment & deskew filters
│   ├── phase2_indic_ocr/              # Phase 2: IndicOCR inference
│   │   ├── __init__.py
│   │   ├── model_loader.py            # Hugging Face snapshot & model initialization
│   │   ├── parser.py                  # Page-level IndicOCR inference wrapper
│   │   └── checkpoint_manager.py      # Resumption & crash-recovery tracker
│   ├── phase3_text_verification/      # Phase 3: LLM Verification & Patch Gen
│   │   ├── __init__.py
│   │   ├── llm_client.py              # llama-server / llama-cli wrapper
│   │   ├── prompts.py                 # Gujarati proofreading system prompts
│   │   ├── patch_generator.py         # Unified diff (.patch) & JSON generator
│   │   ├── patch_applier.py           # Selective, interactive, or batch patch applier
│   │   └── report_builder.py          # HTML visual diff report generator
│   ├── phase4_export/                 # Phase 4: Production artifacts
│   │   ├── __init__.py
│   │   ├── sandwich_pdf.py            # Invisible Unicode text layer injector
│   │   └── text_aggregator.py         # Book-level Markdown and FTS indexer
│   └── utils/
│       ├── __init__.py
│       └── logger.py
├── scripts/
│   ├── run_phase1.py                  # CLI to run Phase 1 (PDF -> Images)
│   ├── run_phase2.py                  # CLI to run Phase 2 (Images -> Raw OCR)
│   ├── run_phase3_verify.py           # CLI to run Phase 3 (Raw OCR -> Patches/Diffs)
│   ├── apply_patches.py               # CLI to review & apply patches into verified/
│   └── run_full_pipeline.py           # End-to-end orchestrator with pause-for-review
├── .env.example                       # HF_TOKEN, LLM_ENDPOINT, model paths
├── requirements.txt                   # Python dependencies
└── PLAN.md                            # This plan document
```

---

## 4. Detailed Phase Specifications

### Phase 1: PDF to High-Resolution Images

#### Goals
- Reliably convert multi-page (often 100+ pages) PDFs into optimized images without memory exhaustion.
- Preserve sharp typographical details of complex Gujarati conjuncts (જોડાક્ષર) and diacritics (હ્રસ્વ/દીર્ઘ માત્રા, અનુસ્વાર).

#### Key Specifications
1. **Engine**: `PyMuPDF` (`fitz`) — High performance, low RAM footprint.
2. **Resolution**: Default **300 DPI** (Matrix scaling: `scale = 300 / 72 ≈ 4.166`).
3. **Format**: Lossless compressed PNG.
4. **Multiprocessing**: Parallel page extraction using available CPU cores.
5. **Metadata Manifest (`manifest.json`)**: Tracks page count, hashes, and image dimensions.

#### CLI Command
```bash
python scripts/run_phase1.py --input "books/Nari Ratno (SGVP).pdf" --dpi 300
```

---

### Phase 2: Scanning Images with `bodhan-ai/indic-ocr`

#### Goals
- Transcribe visual Gujarati text accurately into standard UTF-8 Unicode characters.
- Detect dual-column layouts (like `Aadarsh bhaktgatha.pdf`) without cross-column bleeding.
- Store raw OCR output immutably.

#### Model Architecture
- **Stage A (`IndicDocLayout`)**: PP-DocLayoutV3 / RT-DETR (33M params, 133MB) for block classification (37 categories) and reading order.
- **Stage B (`IndicBlockOCR`)**: Qwen3.5-0.8B + Sarvam-30B tokenizer (0.8B params, 1.7GB) for Gujarati Unicode transcription.

#### Output
- `raw/json/page_XXXX.json`: Bounding boxes (`bbox_xyxy`), confidence, and raw text.
- `raw/markdown/page_XXXX.md`: Raw reading-ordered Markdown.
- **Note**: These files are NEVER overwritten by verification.

#### CLI Command
```bash
python scripts/run_phase2.py --images-dir data/images/Nari_Ratno_SGVP/ --output-dir data/ocr_output/Nari_Ratno_SGVP/raw/
```

---

### Phase 3: Local LLM Verification & Patch Generation

#### Concept: Audit & Propose, Do Not Blindly Overwrite
The Local LLM (Gemma 4 E2B via `llama-server` or `llama-cli`) acts as an auditor. It compares the raw OCR against Gujarati grammar and vocabulary, and outputs **proposed patches**.

#### Output Artifacts per Page / Book
1. **Unified Diff File (`page_XXXX.patch` and `book_full.patch`)**:
   Standard POSIX-compliant unified diff file:
   ```diff
   --- a/raw/markdown/page_0014.md
   +++ b/verified/markdown/page_0014.md
   @@ -8,3 +8,3 @@
   - ? દૂધપાક કરે પણ અંદર સાકર ન નાખે તો ! શાક કરે પણ માંહી મીઠું ન હોય તો ?
   + દૂધપાક કરે પણ અંદર સાકર ન નાખે તો ! શાક કરે પણ માંહી મીઠું ન હોય તો ?
   - શરીર હોય પણ અંદર જીવ ન હોય તા ? એ બધું નકામું
   + શરીર હોય પણ અંદર જીવ ન હોય તો ? એ બધું નકામું
   ```
2. **Detailed JSON Change Log (`page_XXXX_diff.json`)**:
   Enables automated analysis and filtering:
   ```json
   {
     "page": 14,
     "changes_count": 1,
     "changes": [
       {
         "line": 8,
         "type": "punctuation_clean",
         "original": "? દૂધપાક કરે પણ",
         "proposed": "દૂધપાક કરે પણ",
         "reason": "Removed stray leading question mark caused by OCR border speckle"
       }
     ]
   }
   ```
3. **Interactive Visual HTML Report (`diff_summary.html`)**:
   - Opens directly in any web browser.
   - Side-by-side view with deletions highlighted in red and additions in green.
   - Summarizes total changes per page with filters: "Punctuation only", "Spelling fixes", "Large edits".

#### Verification Prompt Guardrails
```text
[SYSTEM]
You are an expert Gujarati proofreader for classical and religious literature.
Your task is ONLY to audit OCR output and identify obvious OCR defects.

STRICT INSTRUCTIONS:
1. DO NOT rephrase, summarize, modernize, or translate the text.
2. Maintain sacred terminology (વચનામૃત, સંપ્રદાય, ભક્ત, ધ્યાન, લીલાચરિત્ર) exactly.
3. Identify:
   - Broken ligatures/conjuncts (e.g., 'ભ ક ત' -> 'ભક્ત')
   - Misread matras (e.g., હ્રસ્વ/દીર્ઘ confusion)
   - Accidental spaces splitting single words
   - Stray punctuation created by paper smudges/borders
4. Output the corrected text strictly inside a ```gujarati ... ``` codeblock.
```

#### CLI Command to Generate Patches
```bash
# Generate patch files and HTML report using local llama-server
python scripts/run_phase3_verify.py \
  --raw-dir data/ocr_output/Nari_Ratno_SGVP/raw/ \
  --patches-dir data/ocr_output/Nari_Ratno_SGVP/patches/ \
  --server-url http://127.0.0.1:8080/v1 \
  --model-name gemma-4-e2b
```

---

### Phase 3.5: Patch Review & Application Tooling

Once patches are generated, the user chooses how to apply them:

#### Workflow Options
1. **Interactive CLI Mode (`scripts/apply_patches.py --interactive`)**:
   Prompts the user hunk-by-hunk in the terminal:
   ```text
   [Page 14 | Change 1 of 2]
   - ? દૂધપાક કરે પણ અંદર સાકર ન નાખે તો
   + દૂધપાક કરે પણ અંદર સાકર ન નાખે તો
   Apply this change? [y]es / [n]o / [a]ll remaining / [q]uit: 
   ```
2. **Standard Unix `patch` Tool**:
   Because patches are standard unified diffs, you can use native Linux tooling:
   ```bash
   # Dry-run inspection
   patch --dry-run -p1 -d data/ocr_output/Nari_Ratno_SGVP/ < data/ocr_output/Nari_Ratno_SGVP/patches/book_full.patch

   # Apply all
   patch -p1 -d data/ocr_output/Nari_Ratno_SGVP/ < data/ocr_output/Nari_Ratno_SGVP/patches/book_full.patch
   ```
3. **Rule-Based or Secondary LLM Filter**:
   Run an automated filter script that accepts only low-risk punctuation/whitespace fixes while keeping spelling alterations pending for human review.
4. **Batch Apply After HTML Audit**:
   Once you look through `diff_summary.html` and verify the model didn't hallucinate:
   ```bash
   python scripts/apply_patches.py --input-raw data/ocr_output/Nari_Ratno_SGVP/raw/ \
                                  --patches-dir data/ocr_output/Nari_Ratno_SGVP/patches/ \
                                  --output-verified data/ocr_output/Nari_Ratno_SGVP/verified/ \
                                  --all
   ```

---

### Phase 4: Delivery & Searchable Artifact Generation

#### Deliverables (Built ONLY from Approved Verified Text)
1. **Searchable "Sandwich" PDF**:
   - Injects the approved Unicode text as an invisible layer over the original PDF pages matching the detected bounding boxes (`bbox_xyxy`).
   - Searching on Android or Linux using standard Gujarati keyboard highlights the exact visual words.
2. **Consolidated Book Markdown & Text**:
   - Clean, verified full-text book document ready for publication, e-readers, or RAG search.
3. **SQLite Full-Text Search (FTS5) Database**:
   - Embedded database (`book_search.db`) indexing every word and page coordinate for instant offline search in mobile/desktop apps.

---

## 5. Technical Requirements & Dependencies

### System Prerequisites
- Linux / Android / WSL environment.
- Python 3.10+
- `llama-server` or `llama-cli` (from `llama.cpp`) with Gemma 4 E2B GGUF weights.
- Hugging Face account with access to `bodhan-ai/indic-ocr`.
- Optional: NVIDIA GPU (CUDA); CPU fully supported by llama.cpp and PyMuPDF.

### Python Dependencies (`requirements.txt`)
```text
# PDF & Image processing
PyMuPDF>=1.24.0
Pillow>=10.0.0
opencv-python-headless>=4.8.0

# Hugging Face & IndicOCR
huggingface-hub>=0.24.0
torch>=2.2.0
torchvision>=0.17.0
transformers>=4.40.0
accelerate>=0.28.0

# LLM Client & Diffs
httpx>=0.27.0
openai>=1.25.0
diff-match-patch>=20230430

# Utilities
tqdm>=4.66.0
python-dotenv>=1.0.0
pydantic>=2.6.0
```

---

## 6. Phased Implementation Roadmap

| Phase | Milestone | Deliverables |
| :--- | :--- | :--- |
| **Phase 0** | Environment Setup | Virtual env, `requirements.txt`, `.env` config (HF token, llama-server endpoint). |
| **Phase 1** | PDF to Image Extractor | `src/phase1_pdf_to_images/extractor.py` & CLI `scripts/run_phase1.py` with 300 DPI rendering and `manifest.json`. |
| **Phase 2** | IndicOCR Batch Pipeline | `src/phase2_indic_ocr/parser.py` & CLI `scripts/run_phase2.py` writing immutable `raw/` JSON & Markdown. |
| **Phase 3** | LLM Verification & Patch Gen | `src/phase3_text_verification/patch_generator.py` & CLI `scripts/run_phase3_verify.py` generating `.patch` files, change logs, and visual HTML audit reports. |
| **Phase 3.5**| Patch Review & Applier | `scripts/apply_patches.py` supporting interactive `[y/n]` prompt, Unix `patch` integration, and batch export to `verified/`. |
| **Phase 4.1**| Consolidated Book Exporter | Final verified book Markdown and SQLite FTS5 database generator. |
| **Phase 4.2**| Searchable PDF Generator | `src/phase4_export/sandwich_pdf.py` injecting verified Unicode layer into original PDF pages. |
| **Phase 5** | End-to-End Testing | Complete test on sample pages of `Nari Ratno (SGVP).pdf` and `Aadarsh bhaktgatha.pdf` verifying Gujarati keyboard search in Linux Document Viewer. |
