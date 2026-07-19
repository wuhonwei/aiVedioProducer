from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ComfyImageBackend, ImageBackend, fresh_seed
from aivp.visual.location_profiles import (
    DEFAULT_LOCATION_LORA_WEIGHT,
    read_location_profile,
)
from aivp.visual.look_lock import clamp_denoise, resolve_look_lock
from aivp.visual.lora_staging import stage_project_lora
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import DEFAULT_LORA_WEIGHT, save_profile
from aivp.visual.prompts import (
    build_candidate_prompt,
    candidate_negative_for,
    character_negative_for,
)

# Legacy UI defaults that fight the full-body training captions.
_LEGACY_PROBE_MARKERS = (
    "人物半身特写",
    "upper body portrait",
)

_SHEET_LOOK_MARKERS = (
    "国风动画角色定妆",
    "角色定妆",
    "定妆照",
    "character sheet",
    "turnaround",
)


def _strip_sheet_look_markers(text: str) -> str:
    out = (text or "").strip()
    for marker in _SHEET_LOOK_MARKERS:
        out = out.replace(marker, "")
    return out.strip("；，, ").strip()


def _minimal_character_look(profile: dict) -> str:
    """Wardrobe + hair only — avoid full prompt_zh sheet language in keyframes."""
    appearance = profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {}
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    parts: list[str] = []
    hair = str(appearance.get("hair") or "").strip()
    outfit = str(wardrobe.get("default") or "").strip()
    if hair:
        parts.append(hair)
    if outfit:
        parts.append(f"身着{outfit}")
    return _strip_sheet_look_markers("，".join(parts))


def _lora_basename(profile: dict, vpaths: VisualPaths, character_id: str) -> str | None:
    name = profile.get("lora_file")
    if isinstance(name, str) and name.strip():
        return Path(name).name
    local = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    if local:
        return local[0].name
    return None


def _stage_if_comfy(
    backend: ImageBackend,
    source_dir: Path,
    basename: str | None,
    *,
    settings=None,
) -> str | None:
    """Ensure LoRA basename is visible to ComfyUI LoraLoader."""
    if not basename:
        return None
    if not isinstance(backend, ComfyImageBackend):
        return basename
    return stage_project_lora(source_dir, basename, settings=settings)


def default_probe_prompt(profile: dict) -> str:
    """Match training captions: full-body English locks + trigger + look."""
    return build_candidate_prompt(
        profile,
        "front view, looking at viewer, solo, "
        "head fully visible, face clearly visible, not cropped",
    )


def _probe_user_extra(user_prompt: str, profile: dict) -> str:
    """Keep custom extras; drop legacy half-body Chinese-only UI defaults."""
    text = (user_prompt or "").strip()
    if not text:
        return ""
    if any(m in text for m in _LEGACY_PROBE_MARKERS):
        return ""
    look = str(profile.get("prompt_zh") or "").strip()
    name = str(profile.get("name") or "").strip()
    # Exact look / name alone is already inside build_candidate_prompt.
    if look and text == look:
        return ""
    if name and text == name:
        return ""
    return text


def generate_with_character(
    vpaths: VisualPaths,
    character_id: str,
    prompt: str,
    backend: ImageBackend,
    *,
    negative: str | None = None,
    shot_id: str | None = None,
    is_probe: bool = False,
    settings=None,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    trigger = profile.get("trigger") or ""
    look = (profile.get("prompt_zh") or "").strip()

    ref_image: Path | None = None
    denoise = 1.0
    cfg: float | None = None
    if is_probe:
        full_prompt = default_probe_prompt(profile)
        extra = _probe_user_extra(prompt, profile)
        if extra and extra not in full_prompt:
            full_prompt = f"{full_prompt}, {extra}"
        neg = negative or candidate_negative_for(profile)
        strength = float(profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT)
        # Soft look-lock keeps face/outfit like the train set (candidates used img2img).
        ref_image, lock_denoise = resolve_look_lock(vpaths, character_id, profile)
        if ref_image is not None:
            # Match candidate lock band — raising denoise + LoRA rewrites age/face.
            denoise = clamp_denoise(float(lock_denoise), lo=0.50, hi=0.66)
            cfg = 6.5
        else:
            # Pure txt2img needs a higher LoRA floor against Guofeng priors.
            strength = min(1.0, max(strength, 0.85))
    else:
        full_prompt = f"{trigger}, {prompt}" if trigger and trigger not in prompt else prompt
        if look and look not in full_prompt:
            full_prompt = f"{full_prompt}, {look}"
        neg = negative or profile.get("negative_anchor") or character_negative_for(
            str(profile.get("gender_presentation") or "")
        )
        strength = float(profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT)

    out_dir = vpaths.generations_dir(character_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "probe" if is_probe else "gen"
    name = f"{prefix}_{shot_id or 'free'}_{stamp}.png"
    dest = out_dir / name
    lora = _stage_if_comfy(
        backend,
        vpaths.lora_dir(character_id),
        _lora_basename(profile, vpaths, character_id),
        settings=settings,
    )
    backend.generate(
        prompt=full_prompt,
        negative=neg,
        dest=dest,
        seed=fresh_seed(),
        width=768,
        height=1024,
        lora_name=lora,
        lora_strength=strength,
        ref_image=ref_image,
        denoise=denoise,
        cfg=cfg,
    )
    if is_probe:
        profile["probe_status"] = "pending"
        profile["last_probe_file"] = name
        profile["last_probe_at"] = datetime.now(timezone.utc).isoformat()
        save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "trigger": trigger,
        "prompt": full_prompt,
        "negative": neg,
        "lora_strength": strength,
        "file": name,
        "path": str(dest),
        "is_probe": is_probe,
        "lora_ready": bool(profile.get("lora_ready")),
        "lora_file": lora or profile.get("lora_file"),
        "probe_status": profile.get("probe_status"),
        "used_look_lock": bool(ref_image),
        "denoise": denoise,
    }


def approve_lora(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("train_status") not in ("trained", "package_ready") and not list(
        vpaths.lora_dir(character_id).glob("*.safetensors")
    ):
        # Allow approve when safetensors exists even if status drifted.
        if not profile.get("lora_file"):
            raise ValueError("lora_not_trained")
    if not profile.get("lora_file"):
        local = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
        if local:
            profile["lora_file"] = local[0].name
    profile["probe_status"] = "approved"
    profile["lora_ready"] = True
    profile["status"] = "lora_ready"
    profile["lora_approved_at"] = datetime.now(timezone.utc).isoformat()
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "lora_ready": True,
        "probe_status": "approved",
        "lora_file": profile.get("lora_file"),
    }


def reject_lora(vpaths: VisualPaths, character_id: str, *, note: str = "") -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["probe_status"] = "rejected"
    profile["lora_ready"] = False
    profile["status"] = "trained" if profile.get("train_status") == "trained" else profile.get(
        "status", "curated_ready"
    )
    if note:
        profile["probe_reject_note"] = note
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "lora_ready": False,
        "probe_status": "rejected",
    }


def _location_lora_basename(profile: dict, vpaths: VisualPaths, location_id: str) -> str | None:
    name = profile.get("lora_file")
    if isinstance(name, str) and name.strip():
        return Path(name).name
    local = list(vpaths.location_lora_dir(location_id).glob("*.safetensors"))
    if local:
        return local[0].name
    return None


def generate_shot_with_loras(
    vpaths: VisualPaths,
    backend: ImageBackend,
    *,
    prompt: str,
    location_id: str | None = None,
    character_ids: list[str] | None = None,
    negative: str | None = None,
    shot_id: str | None = None,
    location_strength: float | None = None,
    use_location_lora: bool = False,
    character_look: str = "full",
    prompt_order: str = "identity_first",
    max_character_lora_strength: float | None = None,
    character_lora_strength: float | None = None,
    settings=None,
) -> dict[str, Any]:
    """Txt2img with optional location LoRA first, then character LoRAs stacked."""
    loras: list[dict[str, Any]] = []
    scene_first = prompt_order == "scene_first"

    loc_trigger = ""
    loc_look = ""
    loc_file = None
    if location_id:
        loc_profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
        loc_trigger = str(loc_profile.get("trigger") or "")
        loc_look = str(loc_profile.get("prompt_zh") or "").strip()
        if use_location_lora and loc_profile.get("lora_ready"):
            loc_file = _location_lora_basename(loc_profile, vpaths, location_id)
            if loc_file:
                loc_file = _stage_if_comfy(
                    backend,
                    vpaths.location_lora_dir(location_id),
                    loc_file,
                    settings=settings,
                )
                strength = float(
                    location_strength
                    if location_strength is not None
                    else loc_profile.get("lora_weight_default")
                    or DEFAULT_LOCATION_LORA_WEIGHT
                )
                loras.append({"name": loc_file, "strength": strength})

    char_triggers: list[str] = []
    char_trigger_bits: list[str] = []
    char_look_bits: list[str] = []
    for cid in character_ids or []:
        path = vpaths.profile_json(cid)
        if not path.exists():
            continue
        profile = json.loads(path.read_text(encoding="utf-8"))
        trigger = str(profile.get("trigger") or "")
        if trigger:
            char_triggers.append(trigger)
            char_trigger_bits.append(trigger)
        if character_look == "minimal":
            look = _minimal_character_look(profile)
        else:
            look = str(profile.get("prompt_zh") or "").strip()
        if look and look not in " ".join(char_trigger_bits + char_look_bits):
            char_look_bits.append(look)
        if profile.get("lora_ready"):
            if character_lora_strength is not None:
                strength = float(character_lora_strength)
            else:
                strength = float(
                    profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT
                )
                # Keyframes use minimal look; slightly lower LoRA so scene/env wins.
                if character_look == "minimal":
                    cap = (
                        max_character_lora_strength
                        if max_character_lora_strength is not None
                        else 0.65
                    )
                    strength = max(0.45, min(strength, cap))
            if strength > 0:
                c_lora = _lora_basename(profile, vpaths, cid)
                if c_lora:
                    c_lora = _stage_if_comfy(
                        backend,
                        vpaths.lora_dir(cid),
                        c_lora,
                        settings=settings,
                    )
                    loras.append(
                        {
                            "name": c_lora,
                            "strength": strength,
                        }
                    )

    user_prompt = (prompt or "").strip()
    prompt_bits: list[str] = []
    if scene_first:
        if user_prompt:
            prompt_bits.append(user_prompt)
        prompt_bits.extend(char_trigger_bits)
        prompt_bits.extend(char_look_bits)
        if loc_trigger:
            prompt_bits.append(loc_trigger)
    else:
        if loc_trigger:
            prompt_bits.append(loc_trigger)
        if loc_look:
            prompt_bits.append(loc_look)
        prompt_bits.extend(char_trigger_bits)
        prompt_bits.extend(char_look_bits)
        if user_prompt:
            prompt_bits.append(user_prompt)
    full_prompt = ", ".join(b for b in prompt_bits if b)

    # Prefer character generations dir of first cast, else location generations.
    if character_ids:
        out_dir = vpaths.generations_dir(character_ids[0])
        out_key = character_ids[0]
    elif location_id:
        out_dir = vpaths.location_generations_dir(location_id)
        out_key = location_id
    else:
        raise ValueError("location_id_or_character_ids_required")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"shot_{shot_id or 'free'}_{stamp}.png"
    dest = out_dir / name

    neg = negative or (
        "lowres, blurry, bad anatomy, watermark, text"
        if location_id
        else character_negative_for("")
    )
    primary = loras[0] if loras else None
    backend.generate(
        prompt=full_prompt,
        negative=neg,
        dest=dest,
        seed=fresh_seed(),
        width=1024 if location_id else 768,
        height=768 if location_id else 1024,
        lora_name=primary["name"] if primary else None,
        lora_strength=float(primary["strength"]) if primary else 0.75,
        loras=loras or None,
    )
    return {
        "shot_id": shot_id,
        "location_id": location_id,
        "character_ids": list(character_ids or []),
        "prompt": full_prompt,
        "file": name,
        "path": str(dest),
        "out_key": out_key,
        "loras": loras,
        "location_trigger": loc_trigger,
        "character_triggers": char_triggers,
        "use_location_lora": bool(use_location_lora),
        "location_lora_file": loc_file,
        "prompt_order": prompt_order,
    }
