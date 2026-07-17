from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import save_profile

LOOK_LOCK_FOLDERS = frozenset({"candidates", "sheets", "generations"})
DEFAULT_LOOK_LOCK_DENOISE = 0.48


def look_lock_dir(vpaths: VisualPaths, character_id: str) -> Path:
    return vpaths.character_dir(character_id) / "look_lock"


def look_lock_ref_path(vpaths: VisualPaths, character_id: str) -> Path | None:
    ref = look_lock_dir(vpaths, character_id) / "ref.png"
    return ref if ref.exists() else None


def set_look_lock(
    vpaths: VisualPaths,
    character_id: str,
    *,
    folder: str,
    filename: str,
    denoise: float = DEFAULT_LOOK_LOCK_DENOISE,
) -> dict[str, Any]:
    folder = (folder or "").strip()
    filename = (filename or "").strip()
    if folder not in LOOK_LOCK_FOLDERS:
        raise ValueError(f"invalid_look_lock_folder:{folder}")
    if "/" in filename or "\\" in filename or ".." in filename or not filename.lower().endswith(
        ".png"
    ):
        raise ValueError("invalid_look_lock_filename")
    src = vpaths.character_dir(character_id) / folder / filename
    if not src.exists():
        raise FileNotFoundError(f"look_lock_source_missing:{folder}/{filename}")

    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    dest_dir = look_lock_dir(vpaths, character_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("*"):
        if old.is_file():
            old.unlink()
    dest = dest_dir / "ref.png"
    shutil.copy2(src, dest)
    cap = src.with_suffix(".txt")
    if cap.exists():
        shutil.copy2(cap, dest_dir / "ref.txt")

    strength = max(0.25, min(0.75, float(denoise)))
    profile["look_lock"] = {
        "folder": folder,
        "file": filename,
        "ref_file": "ref.png",
        "denoise": strength,
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "look_lock": profile["look_lock"],
        "ref_path": str(dest),
    }


def clear_look_lock(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.pop("look_lock", None)
    save_profile(vpaths, profile)
    dest_dir = look_lock_dir(vpaths, character_id)
    if dest_dir.exists():
        for old in dest_dir.glob("*"):
            if old.is_file():
                old.unlink()
    return {"character_id": character_id, "look_lock": None}


def resolve_look_lock(
    vpaths: VisualPaths,
    character_id: str,
    profile: dict | None = None,
) -> tuple[Path | None, float]:
    """Return (ref_png_path, denoise) when look lock is active."""
    if profile is None:
        path = vpaths.profile_json(character_id)
        if not path.exists():
            return None, 1.0
        profile = json.loads(path.read_text(encoding="utf-8"))
    lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
    ref = look_lock_ref_path(vpaths, character_id)
    if not lock or not ref:
        return None, 1.0
    denoise = float(lock.get("denoise") or DEFAULT_LOOK_LOCK_DENOISE)
    return ref, max(0.25, min(0.75, denoise))
