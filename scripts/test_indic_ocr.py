#!/usr/bin/env python3
"""
Standalone test script for IndicOCR.
Tests model loading from ~/models/indic-ocr, CUDA execution,
and Gujarati OCR transcription on a sample image.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add the model directory to sys.path
MODEL_PATH = Path(os.path.expanduser("~/models/indic-ocr"))
if not MODEL_PATH.exists():
    print(f"Error: Model path not found at {MODEL_PATH}")
    sys.exit(1)

sys.path.insert(0, str(MODEL_PATH))

import torch
from indic_ocr import IndicOCR

def test_ocr(image_path: str | Path, output_dir: str | Path = "data/test_output"):
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        print(f"Error: Image not found at {image_path}")
        return

    print("=" * 60)
    print(f"IndicOCR Standalone Model Test")
    print(f"Model Path:  {MODEL_PATH}")
    print(f"Image Path:  {image_path}")
    print(f"CUDA Ready:  {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU Device:  {torch.cuda.get_device_name(0)}")
        print(f"Alloc VRAM:  {torch.cuda.memory_allocated(0)/(1024*1024):.1f} MB")
    print("=" * 60)

    print("\n[1/3] Loading IndicOCR model (Layout + Recognizer)...")
    t0 = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    parser = IndicOCR.from_pretrained(MODEL_PATH, device=device)
    load_time = time.time() - t0
    print(f"✓ Model initialized in {load_time:.2f} seconds.")

    print(f"\n[2/3] Running document parsing on {image_path.name}...")
    t1 = time.time()
    result = parser.parse(str(image_path))
    ocr_time = time.time() - t1
    print(f"✓ Inference completed in {ocr_time:.2f} seconds.")

    blocks = result.get("blocks", [])
    markdown = result.get("markdown", "")
    print(f"\n[3/3] Results Summary:")
    print(f"  - Page dimensions: {result.get('width')} x {result.get('height')}")
    print(f"  - Total detected blocks: {len(blocks)}")
    
    # Show block types breakdown
    block_types = {}
    for b in blocks:
        lbl = b.get("label", "Unknown")
        block_types[lbl] = block_types.get(lbl, 0) + 1
    print(f"  - Block types: {block_types}")

    # Save outputs
    stem = image_path.stem
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n✓ Saved JSON result to: {json_path}")
    print(f"✓ Saved Markdown result to: {md_path}")

    print("\n" + "=" * 60)
    print("EXTRACTED GUJARATI MARKDOWN SAMPLE:")
    print("=" * 60)
    lines = markdown.strip().split("\n")
    sample_lines = lines[:25]
    print("\n".join(sample_lines))
    if len(lines) > 25:
        print(f"... ({len(lines) - 25} more lines in {md_path})")
    print("=" * 60)

if __name__ == "__main__":
    default_image = Path("data/images/Aadarsh_bhaktgatha/page_0050.png")
    
    target_img = sys.argv[1] if len(sys.argv) > 1 else default_image
    test_ocr(target_img)
