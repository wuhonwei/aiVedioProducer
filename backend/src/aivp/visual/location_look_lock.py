"""Establishing look-lock for locations."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.location_profiles import read_location_profile, save_location_profile
from aivp.visual.paths import VisualPaths

LOCATION_LOOK_LOCK_FOLDERS = frozenset(
    {"candidates", "sheets", "generations", "curated", "look_lock_archive"}
)
DEFAULT_LOCATION_LOOK_LOCK_DENOISE = 0.55


def location_look_lock_ref_path(vpaths: VisualPaths, location_id: str) -> Path | None:
    path = vpaths.location_dir(location_id) / "look_lock" / "ref.png"
    return path if path.exists() else None


def resolve_location_look_lock(
    vpaths: VisualPaths, location_id: str, profile: dict | None = None
) -> tuple[Path | None, float]:
    ref = location_look_lock_ref_path(vpaths, location_id)
    if not ref:
        return None, 1.0
    denoise = DEFAULT_LOCATION_LOOK_LOCK_DENOISE
    if profile and isinstance(profile.get("look_lock"), dict):
        try:
            denoise = float(profile["look_lock"].get("denoise") or denoise)
        except (TypeError, ValueError):
            pass
    return ref, denoise


def set_location_look_lock(
    vpaths: VisualPaths,
    location_id: str,
    *,
    folder: str,
    filename: str,
    denoise: float = DEFAULT_LOCATION_LOOK_LOCK_DENOISE,
) -> dict[str, Any]:
    folder = (folder or "").strip()
    if folder not in LOCATION_LOOK_LOCK_FOLDERS:
        raise ValueError(f"invalid_look_lock_folder:{folder}")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid_filename")
    src = vpaths.location_dir(location_id) / folder / filename
    if not src.exists():
        raise FileNotFoundError(f"look_lock_source_missing:{folder}/{filename}")
    lock_dir = vpaths.location_dir(location_id) / "look_lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    dest = lock_dir / "ref.png"
    shutil.copy2(src, dest)
    profile = read_location_profile(vpaths.location_profile_json(location_id)) or {
        "location_id": location_id
    }
    lock = {
        "folder": folder,
        "file": filename,
        "ref_file": "ref.png",
        "denoise": float(denoise),
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    profile["look_lock"] = lock
    profile["location_id"] = location_id
    save_location_profile(vpaths, profile)
    return {"look_lock": lock}


def clear_location_look_lock(vpaths: VisualPaths, location_id: str) -> dict[str, Any]:
    profile = read_location_profile(vpaths.location_profile_json(location_id))
    if not profile:
        raise FileNotFoundError(f"profile_missing:{location_id}")
    profile["look_lock"] = None
    save_location_profile(vpaths, profile)
    return {"look_lock": None}
