from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.image_backend import ImageBackend
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
        seed=42,
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
