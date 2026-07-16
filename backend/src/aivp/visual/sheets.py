from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile
from aivp.visual.prompts import (
    EXPRESSION_SLOTS,
    SHEET_NEGATIVE,
    TURNAROUND_SLOTS,
    build_character_prompt,
)


def _basename(path_str: str) -> str:
    return Path(path_str).name.strip()


def _lora_name(profile: dict, vpaths: VisualPaths, character_id: str) -> str | None:
    name = profile.get("lora_file")
    if isinstance(name, str) and name.strip():
        return _basename(name)
    local = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    if local:
        return local[0].name
    return None


def generate_character_sheets(
    vpaths: VisualPaths,
    character: dict,
    backend: ImageBackend,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    profile = ensure_profile(vpaths, character)
    cid = profile["character_id"]
    out_dir = vpaths.sheets_dir(cid)
    out_dir.mkdir(parents=True, exist_ok=True)
    trigger = str(profile.get("trigger") or "")
    look = str(profile.get("prompt_zh") or profile.get("name") or "")
    lora = _lora_name(profile, vpaths, cid)
    slots = list(TURNAROUND_SLOTS) + list(EXPRESSION_SLOTS)
    created: list[dict[str, str]] = []
    total = len(slots)
    for i, (key, label, framing) in enumerate(slots):
        if should_cancel and should_cancel():
            break
        prompt = build_character_prompt(trigger, look, framing)
        dest = out_dir / f"sheet_{key}.png"
        backend.generate(
            prompt=prompt,
            negative=SHEET_NEGATIVE,
            dest=dest,
            seed=2000 + i,
            width=768,
            height=1024,
            lora_name=lora,
            lora_strength=0.75,
        )
        meta = {
            "key": key,
            "label": label,
            "file": dest.name,
            "prompt": prompt,
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        created.append({"key": key, "label": label, "file": dest.name})
        if on_progress:
            on_progress(i + 1, total)
    profile["status"] = "sheets_ready"
    profile["sheets_generated_at"] = datetime.now(timezone.utc).isoformat()
    vpaths.profile_json(cid).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"character_id": cid, "files": created, "trigger": trigger}
