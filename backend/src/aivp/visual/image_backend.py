from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import httpx

# Comfy/SD seeds are usually 32-bit unsigned; keep positive int32 for API safety.
_SEED_MAX = 2_147_483_647


def fresh_seed() -> int:
    """New random seed per generate call / batch base (avoid fixed 1000+i lock-in)."""
    return random.randint(0, _SEED_MAX)


class ImageBackend(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        negative: str,
        dest: Path,
        seed: int | None = None,
        width: int = 768,
        height: int = 1024,
        lora_name: str | None = None,
        lora_strength: float = 0.75,
    ) -> Path: ...

    def healthy(self) -> bool: ...


class StubImageBackend:
    """Deterministic placeholder images so the visual pipeline works without ComfyUI."""

    def healthy(self) -> bool:
        return True

    def generate(
        self,
        *,
        prompt: str,
        negative: str,
        dest: Path,
        seed: int | None = None,
        width: int = 768,
        height: int = 1024,
        lora_name: str | None = None,
        lora_strength: float = 0.75,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            raise RuntimeError("pillow_required_for_stub_backend") from None

        w = max(64, int(width))
        h = max(64, int(height))
        img = Image.new("RGB", (w, h), color=(30 + (seed or 0) % 40, 50, 70))
        draw = ImageDraw.Draw(img)
        title = (prompt or "character")[:80]
        draw.rectangle((40, 40, w - 40, 180), outline=(220, 200, 160), width=3)
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
        draw.text((56, h - 64), f"seed={seed or 0}", fill=(180, 170, 150))
        if lora_name:
            draw.text((56, h - 36), f"lora={lora_name}", fill=(180, 170, 150))
        img.save(dest, format="PNG")
        meta = dest.with_suffix(".json")
        meta.write_text(
            json.dumps(
                {
                    "prompt": prompt,
                    "negative": negative,
                    "seed": seed,
                    "backend": "stub",
                    "width": w,
                    "height": h,
                    "lora_name": lora_name,
                    "lora_strength": lora_strength,
                },
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
    width: int = 768,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 8.0,
    filename_prefix: str = "aivp",
    lora_name: str | None = None,
    lora_strength: float = 0.75,
) -> dict[str, Any]:
    """ComfyUI API-format graph for SDXL txt2img (GuoFeng / similar)."""
    ckpt = (checkpoint or "").strip()
    if not ckpt:
        raise RuntimeError("comfy_checkpoint_empty")

    model_src: list[Any] = ["4", 0]
    clip_src: list[Any] = ["4", 1]
    nodes: dict[str, Any] = {
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
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }

    lora = (lora_name or "").strip()
    if lora:
        nodes["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora,
                "strength_model": float(lora_strength),
                "strength_clip": float(lora_strength),
                "model": ["4", 0],
                "clip": ["4", 1],
            },
        }
        model_src = ["10", 0]
        clip_src = ["10", 1]

    nodes["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt, "clip": clip_src},
    }
    nodes["7"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative, "clip": clip_src},
    }
    nodes["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": int(seed),
            "steps": int(steps),
            "cfg": float(cfg),
            "sampler_name": "dpmpp_2m_sde",
            "scheduler": "karras",
            "denoise": 1,
            "model": model_src,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    }
    return nodes


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

    def generate(
        self,
        *,
        prompt: str,
        negative: str,
        dest: Path,
        seed: int | None = None,
        width: int = 768,
        height: int = 1024,
        lora_name: str | None = None,
        lora_strength: float = 0.75,
    ) -> Path:
        if not self.healthy():
            raise RuntimeError("comfyui_unreachable")
        if not (self.checkpoint or "").strip():
            raise RuntimeError(
                "comfy_checkpoint_empty: set AIVP_COMFY_CHECKPOINT to your "
                "checkpoint filename under ComfyUI/models/checkpoints "
                "(e.g. Guofeng4.2XL.safetensors)"
            )

        client_id = uuid.uuid4().hex
        resolved_seed = int(seed) if seed is not None else fresh_seed()
        workflow = build_sdxl_txt2img_workflow(
            checkpoint=self.checkpoint,
            prompt=prompt,
            negative=negative or "lowres, blurry, bad anatomy, watermark",
            seed=resolved_seed,
            width=width,
            height=height,
            lora_name=lora_name,
            lora_strength=lora_strength,
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
                        "seed": resolved_seed,
                        "checkpoint": self.checkpoint,
                        "backend": "comfy",
                        "prompt_id": prompt_id,
                        "comfy_file": meta,
                        "width": width,
                        "height": height,
                        "lora_name": lora_name,
                        "lora_strength": lora_strength,
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
