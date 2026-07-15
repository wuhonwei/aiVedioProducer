# Fresh project-only ComfyUI (Windows)

Do **not** point AIVP at an old shared Comfy on 8188. This project uses a new install under 	ools/ComfyUI on port **8190**.

## 1. Clone

From the repo root:

`powershell
New-Item -ItemType Directory -Force -Path tools | Out-Null
git clone https://github.com/comfyanonymous/ComfyUI.git tools\\ComfyUI
`

## 2. Python deps

Prefer a venv inside the Comfy tree:

`powershell
cd tools\\ComfyUI
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
# GPU: install CUDA torch from https://pytorch.org matching your driver, then:
pip install -r requirements.txt
`

## 3. Checkpoint

Put GuoFeng into this instance only (copy or hardlink — do not start the old Comfy):

`	ext
tools\\ComfyUI\\models\\checkpoints\\Guofeng4.2XL.safetensors
`

Example hardlink from an existing weights file (instance stays 	ools\\ComfyUI):

`powershell
mklink /H tools\\ComfyUI\\models\\checkpoints\\Guofeng4.2XL.safetensors D:\\path\\to\\Guofeng4.2XL.safetensors
`

## 4. Start

`powershell
.\\scripts\\start-comfy.ps1
`

Then set ackend\\.env:

`env
AIVP_IMAGE_BACKEND=comfy
AIVP_COMFY_BASE_URL=http://127.0.0.1:8190
AIVP_COMFY_CHECKPOINT=Guofeng4.2XL.safetensors
`

Restart the AIVP backend and use Visual 试生成。
