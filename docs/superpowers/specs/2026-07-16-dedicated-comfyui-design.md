# Dedicated ComfyUI for aiVedioProducer

## Goal

Run a **fresh, project-only** ComfyUI instance so models, outputs, and port are not shared with other projects on the same machine. Do **not** reuse an existing global Comfy install.

## Layout

| Item | Value |
|------|--------|
| Install path | `tools/ComfyUI/` (gitignored; not committed) |
| Listen | `127.0.0.1:8190` (avoid common `8188`) |
| Checkpoints | `tools/ComfyUI/models/checkpoints/` only for this instance |
| Outputs | `tools/ComfyUI/output/` |
| Backend URL | `AIVP_COMFY_BASE_URL=http://127.0.0.1:8190` |

Repo commits scripts + docs + `.env.example` only. Comfy source and weights stay local.

## Runtime

- Native Windows ComfyUI (official clone), not Docker, not an old shared install.
- Start via `scripts/start-comfy.ps1` with `--listen 127.0.0.1 --port 8190`.
- App image path already posts API-format workflows (`ComfyImageBackend`); no change to t2i business logic beyond env defaults.

## Config defaults (`.env.example`)

- `AIVP_IMAGE_BACKEND=comfy`
- `AIVP_COMFY_BASE_URL=http://127.0.0.1:8190`
- `AIVP_COMFY_CHECKPOINT=Guofeng4.2XL.safetensors`

## One-time local setup

1. Clone ComfyUI into `tools/ComfyUI` and install its Python deps (CUDA torch as needed).
2. Place `Guofeng4.2XL.safetensors` under `tools/ComfyUI/models/checkpoints/` (copy or hardlink from shared weights is OK; do not reuse the old Comfy process).
3. Start Comfy with `scripts/start-comfy.ps1`, then the AIVP backend; probe / 试生成 uses this instance.

## Out of scope

- Embedding Comfy inside the `aivp` Python package
- Committing model weights or the Comfy tree
- Changing shot/LoRA training pipelines beyond pointing at this URL
