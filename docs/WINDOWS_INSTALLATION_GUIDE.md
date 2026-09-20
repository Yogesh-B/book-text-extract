# Windows Installation & Setup Guide with CUDA Acceleration

This guide walks you through setting up and running the **IndicOCR Text Extraction Pipeline** on **Windows 10 / Windows 11 (64-bit)** with full **NVIDIA CUDA GPU acceleration**.

---

## 1. System Requirements

| Component | Minimum | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **OS** | Windows 10 (Build 19041+) or Windows 11 (64-bit) | Windows 11 (64-bit) | Ensure PowerShell 5.1+ or Windows Terminal is available. |
| **GPU** | NVIDIA GPU (Turing / Ampere / Ada / Blackwell) with **6GB+ VRAM** | NVIDIA GPU with **8GB - 16GB+ VRAM** (RTX 3060, 4070, 4080, etc.) | Compute capability >= 7.0 is recommended for PyTorch. |
| **RAM** | 16 GB | 32 GB | High-DPI PDF rasterization requires ample system memory. |
| **Disk** | 20 GB free space (SSD) | 50 GB+ free space (NVMe SSD) | Models, PyTorch packages, and intermediate renders take several GBs. |
| **Python** | Python 3.10 or 3.11 (64-bit) | Python 3.11.x (64-bit) | **Do not** use Python 3.12+ or 32-bit versions. |

---

## 2. Prerequisites: Drivers & Developer Tools

### Step 1: Install or Update NVIDIA Display Drivers
1. Open your browser and navigate to [NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx).
2. Select your GPU series and download the latest **Game Ready Driver** or **Studio Driver**.
3. Install the driver and restart your PC if prompted.
4. Verify driver installation by opening **PowerShell** or **Command Prompt** and running:
   ```powershell
   nvidia-smi
   ```
   *You should see your GPU model, Driver Version, and the supported maximum CUDA version (e.g., `CUDA Version: 12.4` or `12.6`).*

---

### Step 2: Install Visual Studio Build Tools (C++ Compiler)
Certain Python libraries (e.g. PyMuPDF, compiled PyTorch extensions, Hugging Face tokenizers) require Microsoft C++ build tools on Windows.

1. Download the **Visual Studio Build Tools Installer** from [Visual Studio Downloads](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
2. Run the installer and check **Desktop development with C++** (includes MSVC compiler and Windows SDK).
3. Complete the installation.

---

### Step 3: Install Git for Windows
1. Download Git from [git-scm.com](https://git-scm.com/download/win).
2. During setup, select **Git from the command line and also from 3rd-party software**.
3. Enable Long Paths:
   ```powershell
   git config --system core.longpaths true
   ```

---

### Step 4: Install Python 3.11 (64-bit)
1. Download Python 3.11 installer from [python.org](https://www.python.org/downloads/windows/).
2. **IMPORTANT CHECKBOXES during installation**:
   - Check **"Add python.exe to PATH"** (bottom checkbox).
   - Click **Customize installation** -> make sure `pip` and `tcl/tk` are checked.
   - On the Advanced Options screen, check **"Install for all users"** or install to a simple path like `C:\Python311` (avoid paths with spaces).
   - At the end of the installation, click **"Disable path length limit"**.
3. Verify Python in PowerShell:
   ```powershell
   python --version
   # Expected: Python 3.11.x
   ```

---

## 3. Clone Repository & Environment Setup

Open **PowerShell** (or Windows Terminal) in your desired workspace folder (e.g., `C:\Projects`):

```powershell
cd C:\Projects
git clone https://github.com/Yogesh-B/book-text-extract.git
cd book-text-extract
```

### Step 1: Create Virtual Environment
```powershell
python -m venv .venv
```

### Step 2: Enable Execution Policy & Activate Virtual Environment
By default, Windows blocks script execution in PowerShell. Allow local scripts for your user or current process:

```powershell
# Temporarily allow scripts in current session:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force

# Or enable for CurrentUser permanently:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force

# Activate venv:
.venv\Scripts\Activate.ps1
```
*(If you are using classic Command Prompt `cmd.exe`, run: `.venv\Scripts\activate.bat`)*

When activated, your prompt will show `(.venv)`.

---

## 4. Install PyTorch with CUDA Support (Windows)

> [!IMPORTANT]
> **Do not** run plain `pip install torch`! That downloads the CPU-only version. You must specify the official PyTorch CUDA index URL.

Check your GPU driver CUDA capability from `nvidia-smi`. For modern GPUs on Windows, **CUDA 12.1** or **CUDA 12.4** is standard.

Run the appropriate command inside your activated `(.venv)`:

### Option A: PyTorch with CUDA 12.4 (Recommended for RTX 30xx / 40xx)
```powershell
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### Option B: PyTorch with CUDA 12.1
```powershell
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Verify CUDA inside Python
Run this quick one-liner:
```powershell
python -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```
**Expected Output:**
```text
CUDA Available: True
Device Name: NVIDIA GeForce RTX ... (your GPU name)
```

---

## 5. Install Project Dependencies & Model Weights

### Step 1: Install requirements.txt
Install project packages into the virtual environment:
```powershell
pip install -r requirements.txt
```

### Step 2: Install IndicOCR Dependencies
IndicOCR relies on Hugging Face transformers, accelerate, and image layout packages:
```powershell
pip install transformers accelerate timm onnxruntime opencv-python-headless
```

### Step 3: Download IndicOCR Model Weights
The pipeline looks for model weights at `models/indic-ocr` or `C:\Users\<YourUsername>\models\indic-ocr` (or via environment variable `INDIC_OCR_MODEL_PATH`).

Create a `models` directory inside the project:
```powershell
mkdir models
```

Download the weights from Hugging Face (`bodhan-ai/indic-ocr`). You can use Git LFS or the `huggingface_hub` Python CLI:

```powershell
pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='bodhan-ai/indic-ocr', local_dir='models/indic-ocr', local_dir_use_symlinks=False)"
```

---

## 6. Configure Environment Variables (`.env`)

Create your `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

Open `.env` in Notepad or your editor:
```powershell
notepad .env
```

Set paths and options for Windows:
```env
# Optional: explicitly set model path if not in models/indic-ocr
INDIC_OCR_MODEL_PATH=models/indic-ocr

# PyTorch CUDA Memory Allocation flag (critical on Windows to avoid OOM fragmentation)
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

---

## 7. Verify Setup with Standalone Test Script

Test if IndicOCR initializes and detects your NVIDIA GPU correctly:

```powershell
python scripts/test_indic_ocr.py
```

Check the terminal output:
- `CUDA Ready: True`
- `GPU Device: NVIDIA ...`
- `Model initialized in ... seconds`

---

## 8. Running the Pipeline on Windows

### Phase 1: Convert PDF to High-Res Images (300 DPI)
Place your target PDF in the `books/` folder (e.g. `books/sample.pdf`):

```powershell
python scripts/run_phase1.py --input "books/sample.pdf" --dpi 300 --workers 4
```
*Tip: On Windows, set `--workers` to 4 or 8 depending on your CPU core count.*

---

### Phase 2: Run IndicOCR Extraction on GPU
Run OCR on the generated page images:

```powershell
python scripts/run_phase2.py --book "sample" --crop-batch-size 16
```

#### Tuning `--crop-batch-size` based on your Windows GPU VRAM:
| VRAM | Recommended `--crop-batch-size` |
| :--- | :--- |
| **4 GB - 6 GB** | `4` or `8` (prevents CUDA OOM) |
| **8 GB - 12 GB** | `16` |
| **16 GB - 24 GB+** | `32` |

---

### Running Safe Batch Processing (PowerShell Equivalent)
If you have multiple books listed in a text file (like `temp/all_books.txt`), you can run a batch loop in PowerShell that processes each book, runs OCR, and cleans up images to save disk space:

```powershell
# safe_batch.ps1
$Books = Get-Content "temp\all_books.txt"

foreach ($book in $Books) {
    if ([string]::IsNullOrWhiteSpace($book) -or $book.StartsWith("#")) { continue }
    $pdfPath = "books\$book"
    if (-not (Test-Path $pdfPath)) {
        Write-Warning "File not found: $pdfPath"
        continue
    }

    Write-Host "=== Processing $book ===" -ForegroundColor Cyan
    
    # Phase 1: Extract Images
    python scripts\run_phase1.py -i "$pdfPath" --workers 4
    
    # Derive book slug
    $bookSlug = python -c "from src.utils.slug import slugify_filename; from pathlib import Path; print(slugify_filename(Path('$pdfPath').name))"
    
    # Phase 2: Run GPU OCR
    python scripts\run_phase2.py -b "$bookSlug" --crop-batch-size 16
    
    # Cleanup images to save disk space
    if (Test-Path "data\images\$bookSlug") {
        Remove-Item -Recurse -Force "data\images\$bookSlug"
        Write-Host "Cleaned up images for $bookSlug" -ForegroundColor Green
    }
}
```

---

## 9. Troubleshooting & Windows-Specific Gotchas

### 1. `CUDA out of memory` (OOM)
- **Fix 1**: Lower `--crop-batch-size` to `8` or `4`.
- **Fix 2**: Ensure `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` is set in PowerShell before running:
  ```powershell
  $env:PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
  ```
- **Fix 3**: Close background GPU-heavy apps (browsers with hardware acceleration, games, Photoshop).

### 2. `Scripts cannot be loaded because running scripts is disabled on this system`
- Cause: PowerShell ExecutionPolicy default.
- Solution: Run:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
  ```

### 3. `FileNotFoundError: [WinError 206] The filename or extension is too long`
- Cause: Windows 260-character path limit.
- Solution:
  1. Open Registry Editor (`regedit.exe`).
  2. Navigate to `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem`.
  3. Set `LongPathsEnabled` to `1`.
  4. Run in PowerShell: `git config --system core.longpaths true`.

### 4. `UnicodeEncodeError: 'charmap' codec can't encode characters`
- Cause: Windows Command Prompt / PowerShell defaulting to legacy codepage (Windows-1252) instead of UTF-8 when printing Gujarati glyphs.
- Solution: Enable UTF-8 encoding in PowerShell:
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $env:PYTHONIOENCODING="utf-8"
  ```

### 5. `torch.cuda.is_available()` returns `False`
- Ensure you uninstalled the CPU version before installing the CUDA wheel:
  ```powershell
  pip uninstall -y torch torchvision torchaudio
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  ```
- Check that your NVIDIA driver supports the CUDA version via `nvidia-smi`.
