"""Location visual profiles — parallel to character profiles, project-isolated."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import atomic_write_json, read_profile_json

DEFAULT_LOCATION_LORA_WEIGHT = 0.7


def location_trigger(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    ascii_part = re.sub(r"[^a-z0-9]+", "", text)
    if ascii_part and re.search(r"[a-z]", ascii_part):
        base = ascii_part[:20]
    else:
        base = "l" + "".join(f"{ord(ch):x}" for ch in (name or "x")[:8])
    return f"{base}_loc_aivp"


def load_major_locations(bible: dict) -> list[dict[str, Any]]:
    locs = bible.get("locations") or []
    majors = [c for c in locs if isinstance(c, dict) and c.get("tier") == "major"]
    if majors:
        return majors
    return [c for c in locs if isinstance(c, dict)][:8]


def read_location_profile(path: Path) -> dict[str, Any] | None:
    return read_profile_json(path)


def save_location_profile(vpaths: VisualPaths, profile: dict[str, Any]) -> dict[str, Any]:
    lid = str(profile.get("location_id") or "")
    if not lid:
        raise ValueError("location_id_required")
    vpaths.ensure_location(lid)
    path = vpaths.location_profile_json(lid)
    atomic_write_json(path, profile)
    return profile


def ensure_location_profile(vpaths: VisualPaths, location: dict) -> dict[str, Any]:
    lid = str(location.get("id") or location.get("location_id") or "")
    if not lid:
        raise ValueError("location_id_required")
    vpaths.ensure_location(lid)
    path = vpaths.location_profile_json(lid)
    existing = read_location_profile(path)
    name = str(location.get("name") or (existing or {}).get("name") or lid)
    if existing:
        profile = dict(existing)
        profile.setdefault("location_id", lid)
        profile.setdefault("name", name)
        profile.setdefault("trigger", location_trigger(name))
        if location.get("prompt_zh") and not profile.get("prompt_zh"):
            profile["prompt_zh"] = location["prompt_zh"]
        save_location_profile(vpaths, profile)
        return profile

    palette = list(location.get("palette") or [])
    materials = list(location.get("materials") or [])
    profile = {
        "location_id": lid,
        "name": name,
        "trigger": location_trigger(name),
        "tier": location.get("tier") or "major",
        "prompt_zh": str(location.get("prompt_zh") or "").strip(),
        "era_mood": str(location.get("era_mood") or "").strip(),
        "time_of_day_default": str(location.get("time_of_day_default") or "").strip(),
        "weather_default": str(location.get("weather_default") or "").strip(),
        "palette": palette,
        "materials": materials,
        "establishing_shot": str(location.get("establishing_shot") or "").strip(),
        "inferred_fields": list(location.get("inferred_fields") or []),
        "train_status": "not_started",
        "bootstrap_status": "not_started",
        "lora_ready": False,
        "lora_weight_default": DEFAULT_LOCATION_LORA_WEIGHT,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not profile["prompt_zh"]:
        bits = [name]
        if profile["era_mood"]:
            bits.append(profile["era_mood"])
        if palette:
            bits.append("色彩" + "/".join(str(p) for p in palette[:4]))
        if materials:
            bits.append("材质" + "/".join(str(m) for m in materials[:4]))
        bits.append("国风场景空镜")
        profile["prompt_zh"] = "，".join(bits)
        inferred = list(profile["inferred_fields"])
        if "prompt_zh" not in inferred:
            inferred.append("prompt_zh")
        profile["inferred_fields"] = inferred
    save_location_profile(vpaths, profile)
    return profile


def location_status(
    vpaths: VisualPaths, location_id: str, profile: dict
) -> dict[str, Any]:
    cand = list(vpaths.location_candidates_dir(location_id).glob("*.png"))
    curated = list(vpaths.location_curated_dir(location_id).glob("*.png"))
    sheets = list(vpaths.location_sheets_dir(location_id).glob("*.png"))
    gens = list(vpaths.location_generations_dir(location_id).glob("*.png"))
    loras = list(vpaths.location_lora_dir(location_id).glob("*.safetensors"))
    look_lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
    look_lock_ready = bool(
        look_lock
        and (vpaths.location_dir(location_id) / "look_lock" / "ref.png").exists()
    )
    archive_dir = vpaths.location_dir(location_id) / "look_lock_archive"
    archive = list(archive_dir.glob("*.png")) if archive_dir.exists() else []
    return {
        **profile,
        "candidate_count": len(cand),
        "curated_count": len(curated),
        "sheet_count": len(sheets),
        "generation_count": len(gens),
        "train_status": profile.get("train_status") or "not_started",
        "bootstrap_status": profile.get("bootstrap_status") or "not_started",
        "bootstrap_warnings": profile.get("bootstrap_warnings") or [],
        "lora_ready": bool(profile.get("lora_ready")),
        "look_lock": look_lock,
        "look_lock_ready": look_lock_ready,
        "look_lock_archive": sorted((p.name for p in archive), reverse=True),
        "lora_files": [p.name for p in loras],
        "candidates": sorted((p.name for p in cand), reverse=True),
        "curated": sorted((p.name for p in curated), reverse=True),
        "sheets": sorted((p.name for p in sheets), reverse=True),
        "generations": sorted((p.name for p in gens), reverse=True),
    }
