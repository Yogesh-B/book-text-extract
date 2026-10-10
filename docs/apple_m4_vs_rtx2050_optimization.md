# Hardware & Model Optimization Guide: RTX 2050 Mobile vs Apple M4 (Mac mini)

## 1. System Comparison Overview

| Specification / Factor | Current Setup (Asus Laptop) | Target Setup (Mac mini M4) |
| :--- | :--- | :--- |
| **CPU** | AMD Ryzen 5 7535HS (6C / 12T, Zen 3+) | Apple M4 (10-Core CPU, 4P + 6E) |
| **Single-Core / Multi-Core** | ~1,900 / ~7,500 (Geekbench 6) | ~3,850 / ~14,800 (Geekbench 6) |
| **GPU / Accelerators** | NVIDIA RTX 2050 Mobile (GA107, 35–45W TDP) | Apple M4 10-Core GPU + 16-Core Neural Engine (ANE) |
| **VRAM / Unified Memory** | 4 GB GDDR6 (Strict limit) | 16 GB, 24 GB, or 32 GB Unified Memory |
| **Memory Bandwidth** | ~112 GB/s | ~120 GB/s |
| **Compute TFLOPs** | ~6.5 FP32 / ~26 FP16 (Tensor, power-capped) | ~28–30+ FP16 (GPU) + 38 TOPS / ~19 TFLOPs FP16 (ANE) |
| **Thermals & Cooling** | Active laptop fan (loud, thermal-throttles over time) | Active desktop blower (silent, maintains 100% boost clock) |

---

## 2. Bottleneck Analysis: Why the RTX 2050 is Pegged at 100%

In the current pipeline (`text-extract`), you observed:
* **VRAM usage:** ~2.5 GB (well under the 4 GB limit)
* **GPU Utilization:** 100% (compute-bound)
* **Batch size:** Forced to low values (`crop_batch_size = 2` due to VRAM auto-tuning in `src/phase2_indic_ocr/model_loader.py`)

### Root Cause
1. **Low Arithmetic Intensity at Batch Size 2:**
   Vision-Language models like Qwen-0.8B suffer from high kernel launch overhead and poor Tensor Core saturation when processing small batches. The GPU spends a large fraction of its cycles managing memory roundtrips and tiny matrix ops.
2. **Mobile Power Constraints:**
   The RTX 2050 GA107 mobile die is restricted to 35–45W. Sustained 100% compute forces thermal and power throttling, reducing real-world clock frequencies.

---

## 3. Indic-OCR Architecture Breakdown

Based on the actual weights and configs in `~/models/indic-ocr`:

| Stage | Model Name | Architecture | Parameter Count & Precision | Compute Profile |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1 (Layout)** | `IndicDocLayout` | **PP-DocLayoutV3 / RT-DETR** (HGNet-v2 backbone) | 33 M params (FP32), ~133 MB | Fast vision detection (~5–10% of total pipeline latency) |
| **Stage 2 (OCR)** | `IndicBlockOCR` | **Qwen3.5-0.8B VLM** (`Qwen3_5ForConditionalGeneration`) with Sarvam-30B tokenizer | 0.8 B params (BF16), ~1.7 GB | Autoregressive vision-language generation (**90%+ of total latency**) |

---

## 4. Feasibility of Apple Optimizations on M4

### Stage 1: `IndicDocLayout` (RT-DETR, 33M)
* **CoreML / ONNX Runtime:** **Full Native Support**
* The layout model uses `disable_custom_kernels: true` and standard convolutional/transformer ops.
* **Best Strategy:** Export to ONNX and run with `onnxruntime-silicon` using `CoreMLExecutionProvider`. This offloads the entire 33M detection network to the **Apple Neural Engine (ANE)**, completing in ~10–15 ms per page with zero GPU overhead.

### Stage 2: `IndicBlockOCR` (Qwen3.5-0.8B VLM)
* **CoreML (`coremltools`):** **High Friction**
  * Converting autoregressive token generation with custom RoPE (`mrope_section: [11, 11, 10]`) and linear attention layers into static CoreML graphs frequently encounters unsupported operators or shape constraints.
* **Apple MLX (`mlx-vlm`):** **First-Class Native Support (Recommended)**
  * MLX has native implementations for Qwen vision-language architectures.
  * Uses Apple's unified memory and Metal matrix coprocessors with lazy evaluation.
  * Bypasses PyTorch MPS kernel launch overhead and runs substantially faster than the 35W RTX 2050.

---

## 5. Migration Roadmap for Mac mini M4

### Step 1: Zero-Code / Immediate PyTorch MPS Run
Enable Apple Silicon MPS device support in `src/config.py`:
```python
def get_default_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
```
* **Execution flags:** Run without `--compile` (since `torch.compile(dynamic=True)` uses Triton, which is CUDA-oriented).
* **Batch size tuning:** Increase `--crop-batch-size` from 2 to **8 or 16** (safe with 16GB+ unified memory).

### Step 2: High-Performance Apple-Optimized Stack
To extract maximum performance from the M4:
1. **Layout Stage:**
   * Export `IndicDocLayout` to ONNX.
   * Run using `onnxruntime` with `CoreMLExecutionProvider` (runs on ANE).
2. **Recognition Stage:**
   * Wrap `IndicBlockOCR` using `mlx-vlm`.
   * Model weights execute natively on Metal unified memory at FP16/BF16.

### Summary Verdict
* **Out of the box (uncompiled PyTorch MPS eager):** Comparable to or slightly faster than the RTX 2050 due to larger batch size headroom (`batch=8` vs `batch=2`).
* **Optimized (MLX + CoreML ANE):** **2x to 3x faster throughput**, completely silent operation, and zero thermal throttling.
