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
from aivp.visual.profiles import ensure_profile, save_profile
from aivp.visual.prompts import (
    EXPRESSION_SLOTS,
    TURNAROUND_SLOTS,
    build_character_prompt,
    sheet_negative_for,
)
from aivp.visual.qa_tuning import load_qa_tuning

ALL_SLOTS: dict[str, tuple[str, str, str]] = {
    key: (key, label, framing)
    for key, label, framing in list(TURNAROUND_SLOTS) + list(EXPRESSION_SLOTS)
}


def resolve_sheet_slots(
    *,
    group: str | None = None,
    slot_keys: list[str] | None = None,
    expression_dims: list[dict] | None = None,
) -> list[tuple[str, str, str]]:
    """Pick sheet slots: explicit keys, bible dims, or group turnaround|expression|all.

    When ``expression_dims`` is non-empty, expression groups use those dims
    (status not rejected/stale) instead of the legacy fixed 8-slot catalog.
    """
    dim_slots = _slots_from_expression_dims(expression_dims)

    if slot_keys:
        out: list[tuple[str, str, str]] = []
        dim_by_id = {s[0]: s for s in dim_slots}
        for key in slot_keys:
            item = dim_by_id.get(key) or ALL_SLOTS.get(key)
            if item:
                out.append(item)
            elif key.startswith("expr_") and dim_slots:
                # Unknown custom dim id with no framing — skip rather than fail hard
                # if other keys resolved; collect unknowns.
                continue
        if not out:
            # Allow unknown expr_* with dims list framing lookup failure → error.
            raise ValueError(f"unknown_sheet_slots:{slot_keys}")
        return out

    g = (group or "all").strip().lower()
    if g in {"turnaround", "三视图"}:
        return list(TURNAROUND_SLOTS)
    if g in {"expression", "expressions", "表情"}:
        return dim_slots if dim_slots else list(EXPRESSION_SLOTS)
    if g in {"all", "全部", ""}:
        expr = dim_slots if dim_slots else list(EXPRESSION_SLOTS)
        return list(TURNAROUND_SLOTS) + expr
    raise ValueError(f"unknown_sheet_group:{group}")


def _slots_from_expression_dims(
    expression_dims: list[dict] | None,
) -> list[tuple[str, str, str]]:
    if not expression_dims:
        return []
    out: list[tuple[str, str, str]] = []
    for dim in expression_dims:
        if not isinstance(dim, dict):
            continue
        status = str(dim.get("status") or "proposed").lower()
        if status in {"rejected", "stale"}:
            continue
        key = str(dim.get("id") or "").strip()
        if not key.startswith("expr_"):
            continue
        label = str(dim.get("label") or key)
        framing = str(dim.get("framing") or "").strip()
        if not framing:
            # Fallback to legacy library framing when id matches.
            legacy = ALL_SLOTS.get(key)
            framing = legacy[2] if legacy else (
                f"{label} facial expression, facial close-up headshot, "
                "complete face forehead to chin, both eyes visible"
            )
        out.append((key, label, framing))
    out.sort(key=lambda t: t[0])
    # Prefer calm first if present.
    out.sort(key=lambda t: (0 if t[0] == "expr_calm" else 1, t[0]))
    return out


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
    slots = resolve_sheet_slots(
        group=group,
        slot_keys=slot_keys,
        expression_dims=character.get("expression_dims")
        if isinstance(character.get("expression_dims"), list)
        else None,
    )
    ref_image, base_denoise = resolve_look_lock(vpaths, cid, profile)
    tuning = load_qa_tuning(vpaths)
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
            slot_key=key,
        )
        use_ref = ref_image if (ref_image and sheet_uses_look_lock_image(key)) else None
        is_expr = key.startswith("expr_")
        ref_kind = "full"
        if use_ref and is_expr:
            # Face crop so img2img starts as a headshot, not full-body composition.
            use_ref = ensure_face_ref(vpaths, cid, ref_image)
            ref_kind = "face"
            prompt = (
                f"{prompt}, same person identity hairstyle and hair color as reference, "
                "complete face fully visible forehead to chin, both eyes visible, "
                "face-only headshot, "
                "dramatically change facial expression to match the emotion described, "
                "different mouth eyes and eyebrows from the reference photo, "
                "keep identity but not the same calm face, "
                "no body no torso no hands, no half-face crop"
            )
        elif use_ref:
            prompt = (
                f"{prompt}, same character identity hairstyle and outfit as reference, "
                "keep full body framing, not a copy of the reference photo"
            )
        elif ref_image and key in {"turnaround_side", "turnaround_back"}:
            # Text-only identity: do not seed front look-lock latent (keeps front pose).
            prompt = (
                f"{prompt}, same character identity hairstyle hair color and outfit as the locked look, "
                "exact requested camera angle only, not a front-facing copy"
            )
        elif is_expr and ref_image and not use_ref:
            # Strong emotions: txt2img so face_ref calm mouth/eyes don't stick.
            prompt = (
                f"{prompt}, same elderly character identity hairstyle and hair color as the locked look, "
                "face-only headshot, complete face forehead to chin, "
                "emotion must match the expression described, exaggerated readable face"
            )
        if tuning.get("outfit_lock_boost") and not is_expr:
            prompt = (
                f"{prompt}, fully clothed, covered torso, exact wardrobe as described, "
                "no shirtless no bare chest"
            )
        dest = out_dir / _unique_sheet_name(key)
        denoise = sheet_denoise_for(key, base_denoise, tuning=tuning) if use_ref else 1.0
        # Side/back always use high CFG even in txt2img mode.
        cfg = sheet_cfg_for(key, tuning=tuning)
        # Square canvas for face headshots; portrait for full-body turnaround.
        width, height = (768, 768) if is_expr else (768, 1024)
        neg = sheet_negative_for(
            str(profile.get("gender_presentation") or ""),
            slot_key=key,
            text_hints=f"{look} {profile.get('name') or ''}",
            age_look=str(profile.get("age_look") or ""),
            name=str(profile.get("name") or ""),
            profile=profile,
        )
        if tuning.get("extra_negative"):
            neg = f"{neg}, {tuning['extra_negative']}"
        backend.generate(
            prompt=prompt,
            negative=neg,
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
    save_profile(vpaths, profile)
    return {
        "character_id": cid,
        "files": created,
        "trigger": trigger,
        "group": group,
        "slot_keys": [s[0] for s in slots],
        "look_lock": bool(ref_image),
        "denoise": base_denoise if ref_image else 1.0,
    }
