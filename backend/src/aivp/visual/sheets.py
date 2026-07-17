from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.look_lock import (
    ensure_face_ref,
    resolve_look_lock,
    sheet_cfg_for,
    sheet_denoise_for,
    sheet_uses_look_lock_image,
)
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
    ref_image, base_denoise = resolve_look_lock(vpaths, cid, profile)
    created: list[dict[str, str]] = []
    total = len(slots)
    seed_base = fresh_seed()
    if on_progress:
        on_progress(0, total)
    for i, (key, label, framing) in enumerate(slots):
        if should_cancel and should_cancel():
            break
        prompt = build_character_prompt(
            trigger,
            look,
            framing,
            gender_presentation=str(profile.get("gender_presentation") or ""),
            profile=profile,
        )
        use_ref = ref_image if (ref_image and sheet_uses_look_lock_image(key)) else None
        is_expr = key.startswith("expr_")
        ref_kind = "full"
        if use_ref and is_expr:
            # Face crop so img2img starts as a headshot, not full-body composition.
            use_ref = ensure_face_ref(vpaths, cid, ref_image)
            ref_kind = "face"
            prompt = (
                f"{prompt}, exact same face hairstyle and hair color as reference, "
                "face-only headshot, only change facial expression, "
                "no body no torso no hands"
            )
        elif use_ref and key in {"turnaround_side", "turnaround_back"}:
            prompt = (
                f"{prompt}, keep same face hairstyle hair color and outfit colors as reference, "
                "MUST change camera angle to the requested view, not a front copy"
            )
        elif use_ref:
            prompt = (
                f"{prompt}, same character identity hairstyle and outfit as reference, "
                "keep full body framing, not a copy of the reference photo"
            )
        dest = out_dir / _unique_sheet_name(key)
        denoise = sheet_denoise_for(key, base_denoise) if use_ref else 1.0
        cfg = sheet_cfg_for(key) if use_ref else 8.0
        # Square canvas for face headshots; portrait for full-body turnaround.
        width, height = (768, 768) if is_expr else (768, 1024)
        backend.generate(
            prompt=prompt,
            negative=sheet_negative_for(
                str(profile.get("gender_presentation") or ""),
                slot_key=key,
                text_hints=f"{look} {profile.get('name') or ''}",
            ),
            dest=dest,
            seed=(seed_base + i) % (2_147_483_647 + 1),
            width=width,
            height=height,
            lora_name=lora,
            lora_strength=0.75,
            ref_image=use_ref,
            denoise=denoise,
            cfg=cfg,
        )
        meta = {
            "key": key,
            "label": label,
            "file": dest.name,
            "prompt": prompt,
            "for_lora": True,
            "look_lock": bool(use_ref),
            "look_lock_ref_kind": ref_kind if use_ref else None,
            "denoise": denoise,
            "cfg": cfg,
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        kind = "turnaround" if key.startswith("turnaround_") else "expression"
        if key == "turnaround_front":
            view_tag = "front view, facing viewer"
        elif key == "turnaround_side":
            view_tag = "side profile view"
        elif key == "turnaround_back":
            view_tag = "back view, from behind"
        else:
            view_tag = label
        caption = (
            f"{trigger}, {look}, {view_tag}, {framing}, "
            f"guofeng anime character {kind} reference, solo, 1person, "
            + (
                "face only headshot, facial close-up, consistent character face"
                if is_expr
                else "consistent character design"
            )
        )
        dest.with_suffix(".txt").write_text(caption.strip(), encoding="utf-8")
        created.append({"key": key, "label": label, "file": dest.name, "kind": kind})
        if on_progress:
            on_progress(len(created), total)
    profile["status"] = "sheets_ready"
    profile["sheets_generated_at"] = datetime.now(timezone.utc).isoformat()
    if ref_image:
        profile["sheets_used_look_lock"] = True
    vpaths.profile_json(cid).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "character_id": cid,
        "files": created,
        "trigger": trigger,
        "group": group,
        "slot_keys": [s[0] for s in slots],
        "look_lock": bool(ref_image),
        "denoise": base_denoise if ref_image else 1.0,
    }
