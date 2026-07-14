from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aivp.visual.image_backend import ImageBackend
from aivp.visual.paths import VisualPaths


def generate_with_character(
    vpaths: VisualPaths,
    character_id: str,
    prompt: str,
    backend: ImageBackend,
    *,
    negative: str = "lowres, blurry, inconsistent face",
    shot_id: str | None = None,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    trigger = profile.get("trigger") or ""
    full_prompt = f"{trigger}, {prompt}" if trigger else prompt
    if profile.get("prompt_zh"):
        full_prompt = f"{full_prompt}, {profile['prompt_zh']}"
    out_dir = vpaths.character_dir(character_id) / "generations"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"gen_{shot_id or 'free'}_{stamp}.png"
    dest = out_dir / name
    backend.generate(prompt=full_prompt, negative=negative, dest=dest, seed=42)
    return {
        "character_id": character_id,
        "trigger": trigger,
        "prompt": full_prompt,
        "file": name,
        "path": str(dest),
        "lora_ready": bool(profile.get("lora_file")),
        "lora_file": profile.get("lora_file"),
    }
