from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import save_profile

LOOK_LOCK_FOLDERS = frozenset({"candidates", "sheets", "generations"})
# Higher default: keep identity/outfit, allow pose & camera to diverge from the ref.
DEFAULT_LOOK_LOCK_DENOISE = 0.62


def clamp_denoise(value: float, *, lo: float = 0.40, hi: float = 0.82) -> float:
    return max(lo, min(hi, float(value)))


def candidate_denoise_for(view: str, base: float, *, index: int = 0) -> float:
    """Per-view denoise so a batch is not near-copies of the look-lock image."""
    v = (view or "").lower()
    boost = 0.0
    if any(k in v for k in ("full body", "walking", "sitting", "standing")):
        boost = 0.08
    elif any(k in v for k in ("side profile", "over the shoulder", "looking away", "three quarter")):
        boost = 0.10
    elif "close-up" in v:
        boost = 0.06
    # Small index jitter so adjacent candidates don't land on the same strength.
    jitter = ((index % 5) - 2) * 0.025
    return clamp_denoise(base + boost + jitter)


def sheet_denoise_for(slot_key: str, base: float) -> float:
    """Raise denoise for large pose/view changes while keeping identity from look-lock."""
    key = (slot_key or "").lower()
    if key == "turnaround_back":
        return clamp_denoise(base + 0.16, hi=0.82)
    if key == "turnaround_side":
        return clamp_denoise(base + 0.12, hi=0.80)
    if key.startswith("expr_"):
        return clamp_denoise(base + 0.10, hi=0.78)
    return clamp_denoise(base)


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

    strength = clamp_denoise(denoise)
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
    # Old default 0.48 was too copy-like; lift only that legacy value.
    if abs(denoise - 0.48) < 1e-6:
        denoise = DEFAULT_LOOK_LOCK_DENOISE
    return ref, clamp_denoise(denoise)
