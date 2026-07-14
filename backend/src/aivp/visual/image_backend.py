from __future__ import annotations

import json
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
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            # Minimal PNG header-less fallback: write PPM then skip — require pillow.
            raise RuntimeError("pillow_required_for_stub_backend") from None

        img = Image.new("RGB", (768, 1024), color=(30 + (seed or 0) % 40, 50, 70))
        draw = ImageDraw.Draw(img)
        title = (prompt or "character")[:80]
        draw.rectangle((40, 40, 728, 180), outline=(220, 200, 160), width=3)
        draw.text((56, 60), "AIVP stub sheet", fill=(240, 230, 210))
        # Pillow default font; inject prompt wrapped.
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
        dest.write_bytes(b"")  # ensure path
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


class ComfyImageBackend:
    def __init__(self, base_url: str, checkpoint: str = ""):
        self.base_url = base_url.rstrip("/")
        self.checkpoint = checkpoint

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, *, prompt: str, negative: str, dest: Path, seed: int | None = None) -> Path:
        # Minimal API: submit workflow is environment-specific. For now, fail clearly
        # if health ok but workflow template missing; caller should fall back.
        if not self.healthy():
            raise RuntimeError("comfyui_unreachable")
        workflow_hint = {
            "prompt": prompt,
            "negative": negative,
            "seed": seed if seed is not None else 0,
            "checkpoint": self.checkpoint,
            "client_id": uuid.uuid4().hex,
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Placeholder until project-specific workflow JSON is installed under visual/comfy/workflows.
        raise RuntimeError(
            "comfy_workflow_not_configured:"
            + json.dumps(workflow_hint, ensure_ascii=False)[:200]
        )


def get_image_backend(settings) -> ImageBackend:
    backend = (getattr(settings, "image_backend", "stub") or "stub").lower()
    if backend == "comfy":
        return ComfyImageBackend(
            getattr(settings, "comfy_base_url", "http://127.0.0.1:8188"),
            checkpoint=getattr(settings, "comfy_checkpoint", "") or "",
        )
    return StubImageBackend()
