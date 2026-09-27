# text-extract

A multi-phase pipeline for extracting, verifying, and delivering searchable Unicode text from Gujarati PDFs — including scanned hardcopy books and legacy non-Unicode encoded documents.

## Overview

Many legacy Gujarati religious and cultural literature PDFs are either:

- **Non-Unicode encoded** — text is selectable but renders as raw ASCII garbage when copied.
- **Scanned hardcopies** — no text layer at all; often dual-column with aging artifacts, skew, and bleed-through.

This pipeline converts such PDFs into clean, searchable UTF-8 Gujarati text using a four-phase approach:

```
PDF → High-Res Images → IndicOCR Transcription → LLM Verification & Patch Gen → Searchable Artifacts
```

## Pipeline Phases

| Phase | Description | Output |
|-------|-------------|--------|
| **1** | PDF → High-resolution PNG images (300 DPI, multiprocessing) | `data/images/<book>/` |
| **2** | IndicOCR layout detection + Gujarati transcription | `data/ocr_output/<book>/raw/` |
| **3** | Local LLM audits OCR and proposes corrections as standard unified diffs | `data/ocr_output/<book>/patches/` |
| **3.5** | Human-in-the-loop patch review and selective application | `data/ocr_output/<book>/verified/` |
| **4** | Searchable "sandwich" PDF, full-text Markdown, SQLite FTS5 index | `dist/` |

> **Zero Silent Overwrites**: Raw OCR output is immutable. Phase 3 only produces patch files; the user applies them explicitly.

## Quick Start

### 1. Install Dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# For GPU (CUDA 12.x — strongly recommended for Phase 2):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and set your HF_TOKEN (required to download bodhan-ai/indic-ocr)
```

### 3. Run the Pipeline

```bash
# Phase 1: PDF → Images
python scripts/run_phase1.py --input "books/Nari Ratno (SGVP).pdf" --dpi 300

# Phase 2: Images → Raw OCR (GPU recommended)
python scripts/run_phase2.py \
  --images-dir data/images/Nari_Ratno_SGVP/ \
  --output-dir data/ocr_output/Nari_Ratno_SGVP/raw/

# Phase 3: Raw OCR → Patch files (requires llama-server running locally)
python scripts/run_phase3_verify.py \
  --raw-dir data/ocr_output/Nari_Ratno_SGVP/raw/ \
  --patches-dir data/ocr_output/Nari_Ratno_SGVP/patches/ \
  --server-url http://127.0.0.1:8080/v1 \
  --model-name gemma-4-e2b

# Phase 3.5: Review and apply patches interactively
python scripts/apply_patches.py \
  --input-raw data/ocr_output/Nari_Ratno_SGVP/raw/ \
  --patches-dir data/ocr_output/Nari_Ratno_SGVP/patches/ \
  --output-verified data/ocr_output/Nari_Ratno_SGVP/verified/ \
  --interactive
```

Or run the full pipeline end-to-end:

```bash
python scripts/run_full_pipeline.py --input "books/Nari Ratno (SGVP).pdf"
```

## System Requirements

- Linux / WSL / macOS
- Python 3.10+
- `llama-server` or `llama-cli` (from [llama.cpp](https://github.com/ggerganov/llama.cpp)) with a Gemma 4 E2B GGUF model
- Hugging Face account with access granted to [`bodhan-ai/indic-ocr`](https://huggingface.co/bodhan-ai/indic-ocr)
- NVIDIA GPU with CUDA strongly recommended for Phase 2; CPU is supported

## OCR Model

Phase 2 uses **`bodhan-ai/indic-ocr`** by Bodhan AI, a two-stage pipeline:

- **Stage A — IndicDocLayout**: PP-DocLayoutV3 / RT-DETR for document layout detection (37 classes, reading order).
- **Stage B — IndicBlockOCR**: Qwen3.5-0.8B + Sarvam-30B tokenizer for Unicode transcription across 23 Indic scripts including Gujarati.

Access requires accepting the [Indic Open Model License v1.0](https://github.com/Bodhan-AI/bodhan-model-info/blob/main/licenses/indic-open-model-license/v1/Indic_Open_Model_License.md) on the model's Hugging Face page.

## Documentation

- [`docs/SCRIPTS_REFERENCE.md`](docs/SCRIPTS_REFERENCE.md) — Full CLI reference for all scripts
- [`docs/environment_versions.md`](docs/environment_versions.md) — Tested environment and version info
- [`PLAN.md`](PLAN.md) — Detailed architecture and implementation plan

## License

The pipeline code in this repository is released under the terms described in [`LICENSE`](LICENSE).

This project integrates third-party components, each governed by their own licenses. By using this software you are also bound by those terms — see [`LICENSE`](LICENSE) for the full component list and links.
