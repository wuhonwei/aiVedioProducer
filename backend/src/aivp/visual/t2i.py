from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.prompts import CHARACTER_NEGATIVE


def _lora_basename(profile: dict, vpaths: VisualPaths, character_id: str) -> str | None:
    name = profile.get("lora_file")
    if isinstance(name, str) and name.strip():
        return Path(name).name
    local = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    if local:
        return local[0].name
    return None


def generate_with_character(
    vpaths: VisualPaths,
    character_id: str,
    prompt: str,
    backend: ImageBackend,
    *,
    negative: str | None = None,
    shot_id: str | None = None,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    trigger = profile.get("trigger") or ""
    look = (profile.get("prompt_zh") or "").strip()
    full_prompt = f"{trigger}, {prompt}" if trigger else prompt
    # Avoid duplicating look text when the UI already embedded prompt_zh in `prompt`.
    if look and look not in full_prompt:
        full_prompt = f"{full_prompt}, {look}"
    out_dir = vpaths.generations_dir(character_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"gen_{shot_id or 'free'}_{stamp}.png"
    dest = out_dir / name
    lora = _lora_basename(profile, vpaths, character_id)
    backend.generate(
        prompt=full_prompt,
        negative=negative or CHARACTER_NEGATIVE,
        dest=dest,
        seed=42,
        width=768,
        height=1024,
        lora_name=lora,
        lora_strength=0.75,
    )
    return {
        "character_id": character_id,
        "trigger": trigger,
        "prompt": full_prompt,
        "file": name,
        "path": str(dest),
        "lora_ready": bool(lora) or bool(profile.get("lora_file")),
        "lora_file": lora or profile.get("lora_file"),
    }
