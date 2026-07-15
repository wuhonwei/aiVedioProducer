from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import httpx


class ImageBackend(Protocol):
    def generate(self, *, prompt: str, negative: str, dest: Path, seed: int | None = None) -> Path: ...

    def healthy(self) -> bool: ...


class StubImageBackend:
    """Deterministic placeholder images so the visual pipeline works without ComfyUI."""

    def healthy(self) -> bool:
        return True

    def generate(self, *, prompt: str, negative: str, dest: Path, seed: int | None = None) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            raise RuntimeError("pillow_required_for_stub_backend") from None

        img = Image.new("RGB", (768, 1024), color=(30 + (seed or 0) % 40, 50, 70))
        draw = ImageDraw.Draw(img)
        title = (prompt or "character")[:80]
        draw.rectangle((40, 40, 728, 180), outline=(220, 200, 160), width=3)
        draw.text((56, 60), "AIVP stub sheet", fill=(240, 230, 210))
        y = 220
        line = ""
        for ch in title:
            line += ch
            if len(line) >= 18:
                draw.text((56, y), line, fill=(230, 220, 200))
                y += 36
                line = ""
        if line:
            draw.text((56, y), line, fill=(230, 220, 200))
        draw.text((56, 960), f"seed={seed or 0}", fill=(180, 170, 150))
        img.save(dest, format="PNG")
        meta = dest.with_suffix(".json")
        meta.write_text(
            json.dumps(
                {"prompt": prompt, "negative": negative, "seed": seed, "backend": "stub"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return dest


def build_sdxl_txt2img_workflow(
    *,
    checkpoint: str,
    prompt: str,
    negative: str,
    seed: int,
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 8.0,
    filename_prefix: str = "aivp",
) -> dict[str, Any]:
    """ComfyUI API-format graph for SDXL txt2img (GuoFeng / similar)."""
    ckpt = (checkpoint or "").strip()
    if not ckpt:
        raise RuntimeError("comfy_checkpoint_empty")
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }


class ComfyImageBackend:
    def __init__(
        self,
        base_url: str,
        checkpoint: str = "",
        *,
        timeout_sec: float = 300.0,
        poll_interval_sec: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.checkpoint = checkpoint
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, *, prompt: str, negative: str, dest: Path, seed: int | None = None) -> Path:
        if not self.healthy():
            raise RuntimeError("comfyui_unreachable")
        if not (self.checkpoint or "").strip():
            raise RuntimeError(
                "comfy_checkpoint_empty: set AIVP_COMFY_CHECKPOINT to your "
                "checkpoint filename under ComfyUI/models/checkpoints "
                "(e.g. Guofeng4.2XL.safetensors)"
            )

        client_id = uuid.uuid4().hex
        workflow = build_sdxl_txt2img_workflow(
            checkpoint=self.checkpoint,
            prompt=prompt,
            negative=negative or "lowres, blurry, bad anatomy, watermark",
            seed=int(seed if seed is not None else 0),
        )
        dest.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=60.0) as client:
            submitted = client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            if submitted.status_code >= 400:
                detail = submitted.text[:500]
                raise RuntimeError(f"comfy_prompt_rejected:{submitted.status_code}:{detail}")
            body = submitted.json()
            prompt_id = body.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"comfy_no_prompt_id:{body}")

            deadline = time.monotonic() + self.timeout_sec
            history_entry: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                hist = client.get(f"{self.base_url}/history/{prompt_id}")
                if hist.status_code == 200:
                    payload = hist.json() or {}
                    entry = payload.get(prompt_id)
                    if entry and entry.get("outputs"):
                        history_entry = entry
                        break
                time.sleep(self.poll_interval_sec)
            if history_entry is None:
                raise RuntimeError(f"comfy_generate_timeout:{prompt_id}")

            images = _first_output_images(history_entry)
            if not images:
                raise RuntimeError(f"comfy_no_output_images:{prompt_id}")
            meta = images[0]
            view = client.get(
                f"{self.base_url}/view",
                params={
                    "filename": meta["filename"],
                    "subfolder": meta.get("subfolder") or "",
                    "type": meta.get("type") or "output",
                },
            )
            if view.status_code >= 400 or not view.content:
                raise RuntimeError(f"comfy_view_failed:{view.status_code}")
            dest.write_bytes(view.content)
            dest.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "prompt": prompt,
                        "negative": negative,
                        "seed": seed,
                        "checkpoint": self.checkpoint,
                        "backend": "comfy",
                        "prompt_id": prompt_id,
                        "comfy_file": meta,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return dest


def _first_output_images(history_entry: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = history_entry.get("outputs") or {}
    for node_out in outputs.values():
        imgs = node_out.get("images") if isinstance(node_out, dict) else None
        if isinstance(imgs, list) and imgs:
            return [i for i in imgs if isinstance(i, dict) and i.get("filename")]
    return []


def get_image_backend(settings) -> ImageBackend:
    backend = (getattr(settings, "image_backend", "stub") or "stub").lower()
    if backend == "comfy":
        return ComfyImageBackend(
            getattr(settings, "comfy_base_url", "http://127.0.0.1:8188"),
            checkpoint=getattr(settings, "comfy_checkpoint", "") or "",
        )
    return StubImageBackend()
