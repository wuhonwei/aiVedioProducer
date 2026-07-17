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
    TURNAROUND_SLOTS,
    build_character_prompt,
    sheet_negative_for,
)

ALL_SLOTS: dict[str, tuple[str, str, str]] = {
    key: (key, label, framing)
    for key, label, framing in list(TURNAROUND_SLOTS) + list(EXPRESSION_SLOTS)
}


def resolve_sheet_slots(
    *,
    group: str | None = None,
    slot_keys: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Pick sheet slots: explicit keys, or group turnaround|expression|all."""
    if slot_keys:
        out: list[tuple[str, str, str]] = []
        for key in slot_keys:
            item = ALL_SLOTS.get(key)
            if item:
                out.append(item)
        if not out:
            raise ValueError(f"unknown_sheet_slots:{slot_keys}")
        return out
    g = (group or "all").strip().lower()
    if g in {"turnaround", "三视图"}:
        return list(TURNAROUND_SLOTS)
    if g in {"expression", "expressions", "表情"}:
        return list(EXPRESSION_SLOTS)
    if g in {"all", "全部", ""}:
        return list(TURNAROUND_SLOTS) + list(EXPRESSION_SLOTS)
    raise ValueError(f"unknown_sheet_group:{group}")


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


def _unique_sheet_name(key: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"sheet_{key}_{stamp}.png"


def generate_character_sheets(
    vpaths: VisualPaths,
    character: dict,
    backend: ImageBackend,
    *,
    group: str | None = "all",
    slot_keys: list[str] | None = None,
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
    slots = resolve_sheet_slots(group=group, slot_keys=slot_keys)
    created: list[dict[str, str]] = []
    total = len(slots)
    for i, (key, label, framing) in enumerate(slots):
        if should_cancel and should_cancel():
            break
        prompt = build_character_prompt(trigger, look, framing)
        dest = out_dir / _unique_sheet_name(key)
        backend.generate(
            prompt=prompt,
            negative=sheet_negative_for(str(profile.get("gender_presentation") or "")),
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
            "for_lora": True,
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        kind = "turnaround" if key.startswith("turnaround_") else "expression"
        caption = (
            f"{trigger}, {look}, {label}, {framing}, "
            f"guofeng anime character {kind} sheet, consistent character design"
        )
        dest.with_suffix(".txt").write_text(caption.strip(), encoding="utf-8")
        created.append({"key": key, "label": label, "file": dest.name, "kind": kind})
        if on_progress:
            on_progress(i + 1, total)
    profile["status"] = "sheets_ready"
    profile["sheets_generated_at"] = datetime.now(timezone.utc).isoformat()
    vpaths.profile_json(cid).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "character_id": cid,
        "files": created,
        "trigger": trigger,
        "group": group,
        "slot_keys": [s[0] for s in slots],
    }
