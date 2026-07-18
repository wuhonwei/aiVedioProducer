from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.location_profiles import (
    DEFAULT_LOCATION_LORA_WEIGHT,
    read_location_profile,
)
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import DEFAULT_LORA_WEIGHT, save_profile
from aivp.visual.prompts import character_negative_for


def _lora_basename(profile: dict, vpaths: VisualPaths, character_id: str) -> str | None:
    name = profile.get("lora_file")
    if isinstance(name, str) and name.strip():
        return Path(name).name
    local = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    if local:
        return local[0].name
    return None


def default_probe_prompt(profile: dict) -> str:
    trigger = profile.get("trigger") or ""
    anchor = profile.get("positive_anchor") or profile.get("prompt_zh") or ""
    parts = [
        trigger,
        "solo",
        "1person",
        "upper body portrait",
        "simple background",
        anchor,
        "consistent character design",
    ]
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = str(p).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return ", ".join(out)


def generate_with_character(
    vpaths: VisualPaths,
    character_id: str,
    prompt: str,
    backend: ImageBackend,
    *,
    negative: str | None = None,
    shot_id: str | None = None,
    is_probe: bool = False,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    trigger = profile.get("trigger") or ""
    look = (profile.get("prompt_zh") or "").strip()
    if is_probe and not (prompt or "").strip():
        prompt = default_probe_prompt(profile)
    full_prompt = f"{trigger}, {prompt}" if trigger and trigger not in prompt else prompt
    if look and look not in full_prompt:
        full_prompt = f"{full_prompt}, {look}"
    out_dir = vpaths.generations_dir(character_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "probe" if is_probe else "gen"
    name = f"{prefix}_{shot_id or 'free'}_{stamp}.png"
    dest = out_dir / name
    lora = _lora_basename(profile, vpaths, character_id)
    neg = negative or profile.get("negative_anchor") or character_negative_for(
        str(profile.get("gender_presentation") or "")
    )
    strength = float(profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT)
    backend.generate(
        prompt=full_prompt,
        negative=neg,
        dest=dest,
        seed=fresh_seed(),
        width=768,
        height=1024,
        lora_name=lora,
        lora_strength=strength,
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
        "file": name,
        "path": str(dest),
        "is_probe": is_probe,
        "lora_ready": bool(profile.get("lora_ready")),
        "lora_file": lora or profile.get("lora_file"),
        "probe_status": profile.get("probe_status"),
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
) -> dict[str, Any]:
    """Txt2img with location LoRA first, then character LoRAs stacked."""
    loras: list[dict[str, Any]] = []
    prompt_bits: list[str] = []
    loc_trigger = ""
    loc_file = None
    if location_id:
        loc_profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
        loc_trigger = str(loc_profile.get("trigger") or "")
        loc_look = str(loc_profile.get("prompt_zh") or "").strip()
        if loc_trigger:
            prompt_bits.append(loc_trigger)
        if loc_look:
            prompt_bits.append(loc_look)
        if loc_profile.get("lora_ready"):
            loc_file = _location_lora_basename(loc_profile, vpaths, location_id)
            if loc_file:
                strength = float(
                    location_strength
                    if location_strength is not None
                    else loc_profile.get("lora_weight_default")
                    or DEFAULT_LOCATION_LORA_WEIGHT
                )
                loras.append({"name": loc_file, "strength": strength})

    char_triggers: list[str] = []
    for cid in character_ids or []:
        path = vpaths.profile_json(cid)
        if not path.exists():
            continue
        profile = json.loads(path.read_text(encoding="utf-8"))
        trigger = str(profile.get("trigger") or "")
        if trigger:
            char_triggers.append(trigger)
            prompt_bits.append(trigger)
        look = str(profile.get("prompt_zh") or "").strip()
        if look and look not in " ".join(prompt_bits):
            prompt_bits.append(look)
        if profile.get("lora_ready"):
            c_lora = _lora_basename(profile, vpaths, cid)
            if c_lora:
                loras.append(
                    {
                        "name": c_lora,
                        "strength": float(
                            profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT
                        ),
                    }
                )

    user_prompt = (prompt or "").strip()
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
        "location_lora_file": loc_file,
    }
