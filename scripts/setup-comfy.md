# Fresh project-only ComfyUI (Windows)

Do **not** point AIVP at an old shared Comfy on 8188. This project uses a new install under `tools/ComfyUI` on port **8190**.

## 1. Clone

From the repo root:

```powershell
New-Item -ItemType Directory -Force -Path tools | Out-Null
git clone https://github.com/comfyanonymous/ComfyUI.git tools\ComfyUI
```


## Smart App Control stubs (image-only)

Windows **Smart App Control** / “应用程序控制策略已阻止此文件” may block unsigned native modules (PyAV, SciPy `_rbfinterp_pythran`, etc.). For **image-only** Comfy on port 8190, install pure-Python stubs:

```powershell
# from repo root, after venv + requirements
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\patch-comfy-sac-stubs.ps1
```

Re-run after recreating `tools\ComfyUI\.venv`. Video/audio nodes and SciPy `RBFInterpolator` will not work with the stubs.


## 2. Python deps

Prefer a venv inside the Comfy tree:

```powershell
cd tools\ComfyUI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# RTX 50-series (5090 / sm_120) needs CUDA 12.8 wheels — NOT cu121/cu124:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

Manual wheel downloads (Python 3.12 / Windows), if pip is slow:

- https://download.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl
- https://download.pytorch.org/whl/cu128/torchvision-0.26.0%2Bcu128-cp312-cp312-win_amd64.whl
- https://download.pytorch.org/whl/cu128/torchaudio-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl

Then: `pip install .\path\to\those.whl` and `pip install -r requirements.txt`.

## 3. Checkpoint

Put GuoFeng into this instance only (copy or hardlink — do not start the old Comfy):

```text
tools\ComfyUI\models\checkpoints\Guofeng4.2XL.safetensors
```

Example hardlink from an existing weights file (instance stays `tools\ComfyUI`):

```powershell
mklink /H tools\ComfyUI\models\checkpoints\Guofeng4.2XL.safetensors D:\path\to\Guofeng4.2XL.safetensors
```

LoRA weights trained by AIVP live under `backend/data/projects/.../lora/`. Before probe/t2i, the backend **stages** them into `tools/ComfyUI/models/loras/` (hardlink or copy). You normally do not need to copy LoRAs by hand. To backfill already-trained files:

```powershell
python .\scripts\stage-project-loras.py
```

## 4. Start

Preferred (avoids PowerShell execution-policy blocks):

- Double-click `start-comfy.bat` in the repo root, or:

```powershell
# from repo root
.\start-comfy.bat
```

Or bypass policy for the `.ps1` once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-comfy.ps1
```

Then set `backend\.env`:

```env
AIVP_IMAGE_BACKEND=comfy
AIVP_COMFY_BASE_URL=http://127.0.0.1:8190
AIVP_COMFY_CHECKPOINT=Guofeng4.2XL.safetensors
```

Restart the AIVP backend and use Visual 试生成.
