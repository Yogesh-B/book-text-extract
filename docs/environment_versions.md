# Environment & Package Versions

> Generated: 2026-09-26

---

## 🖥️ System-Level (CUDA / cuDNN / NVCC)

| Component | Version |
|-----------|---------|
| **GPU** | NVIDIA GeForce RTX 2050 (4 GB VRAM) |
| **NVIDIA Driver** | 615.71.09 |
| **CUDA (system/UMD)** | 13.4 |
| **NVCC** (compiler) | 13.4.92 (built Tue Sep 01, 2026) |
| **cuDNN** (system headers) | 9.26.0 (`libcudnn.so.9.26.0`) |
| **Python (system)** | 3.14.7 |
| **pip (system)** | 26.2.1 |

---

## 🐍 Project Virtual Environment (`.venv`)

> Managed by **uv 0.12.13** — Python **3.11** (CPython 3.11, via `/home/yogesh/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin`)

### Core ML / CUDA Stack

| Package | Installed Version |
|---------|------------------|
| **torch** | `2.14.0` |
| **torchvision** | `0.29.0` |
| **triton** | `3.8.0` |
| **torch CUDA build** | `13.0` |
| **torch cuDNN** | `9.24.0` (92400) |
| `nvidia_cudnn_cu13` | `9.24.0.43` |
| `nvidia_cublas` | `13.1.1.3` |
| `nvidia_cuda_runtime` | `13.0.96` |
| `nvidia_cuda_nvrtc` | `13.0.88` |
| `nvidia_cuda_cupti` | `13.0.85` |
| `nvidia_cufft` | `12.0.0.61` |
| `nvidia_curand` | `10.4.0.35` |
| `nvidia_cusolver` | `12.0.4.66` |
| `nvidia_cusparse` | `12.6.3.3` |
| `nvidia_cusparselt_cu13` | `0.8.1` |
| `nvidia_nccl_cu13` | `2.30.7` |
| `nvidia_nvshmem_cu13` | `3.4.5` |
| `nvidia_nvjitlink` | `13.4.52` |
| `nvidia_nvtx` | `13.0.85` |
| `nvidia_cufile` | `1.15.1.6` |
| `cuda_bindings` | `13.4.1` |
| `cuda_toolkit` | `13.0.3.0` |
| `cuda_pathfinder` | `1.8.1` |

> ⚠️ **Note:** PyTorch compiled against CUDA **13.0**, while system NVCC is **13.4** — minor mismatch, generally compatible.

### Flash Attention / Linear Attention

| Package | Installed Version | Note |
|---------|------------------|------|
| `flash_linear_attention` | `0.5.2` | ⚠️ Different from `flash-attn` (Dao-AILab) |
| `causal_conv1d` | `1.7.0` | Dependency of flash_linear_attention |
| `fla_core` | `0.5.2` | Core of flash_linear_attention |

> ❌ **`flash-attn` (Dao-AILab / `pip install flash-attn`) is NOT installed.**

### Hugging Face Stack

| Package | Installed Version |
|---------|------------------|
| **transformers** | `5.17.0` |
| **accelerate** | `1.15.0` |
| **huggingface_hub** | `1.31.0` |
| **tokenizers** | `0.23.2` |
| **safetensors** | `0.8.0` |

### Vision / Document Processing

| Package | Installed Version |
|---------|------------------|
| **PyMuPDF** (fitz) | `1.28.2` |
| **Pillow** | `12.3.0` |
| **opencv-python-headless** | `5.0.0.93` |

### Utilities / API

| Package | Installed Version |
|---------|------------------|
| **numpy** | `2.4.6` |
| **scipy** | `1.17.1` |
| **einops** | `0.8.2` |
| **httpx** | `0.28.1` |
| **pydantic** | `2.13.5` |
| **pydantic_core** | `2.46.5` |
| **python-dotenv** | `1.2.3` |
| **tqdm** | `4.70.1` |
| **pyyaml** | `6.0.3` |
| **rich** | `15.0.0` |
| **ninja** | `1.13.2` |
| **sympy** | `1.14.0` |
| **mpmath** | `1.3.0` |
| **networkx** | `3.6.1` |
| **packaging** | `26.3` |
| **psutil** | `7.2.2` |
| **filelock** | `3.32.6` |
| **fsspec** | `2026.7.0` |
| **jinja2** | `3.1.6` |
| **regex** | `2026.9.10` |
| **certifi** | `2026.7.22` |
| **anyio** | `4.15.1` |
| **click** | `8.5.0` |
| **typer** | `0.27.2` |
| **rich** | `15.0.0` |
| **setuptools** | `84.0.0` |
| **typing_extensions** | `4.16.0` |

---

## ❌ Missing Packages (in requirements.txt but NOT installed)

| Package | Required Version | Status |
|---------|-----------------|--------|
| `torchaudio` | `>=2.2.0` | ❌ Not installed |
| `timm` | `>=0.9.0` | ❌ Not installed |
| `onnxruntime` | `>=1.17.0` | ❌ Not installed |
| `sentencepiece` | `>=0.2.0` | ❌ Not installed |
| `openai` | `>=1.25.0` | ❌ Not installed |
| `diff-match-patch` | `>=20230430` | ❌ Not installed |
| `bitsandbytes` | *(optional)* | ❌ Not installed |
| `peft` | *(optional)* | ❌ Not installed |
| `datasets` | *(optional)* | ❌ Not installed |
| `xformers` | *(optional)* | ❌ Not installed |
| `flash-attn` (Dao-AILab) | `>=2.5.0` | ❌ Not installed (flash_linear_attention installed instead) |
