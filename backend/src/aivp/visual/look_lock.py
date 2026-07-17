from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import save_profile

LOOK_LOCK_FOLDERS = frozenset({"candidates", "sheets", "generations"})
# Base for front / soft identity; view/pose slots use higher denoise on top.
DEFAULT_LOOK_LOCK_DENOISE = 0.55


def clamp_denoise(value: float, *, lo: float = 0.40, hi: float = 0.96) -> float:
    return max(lo, min(hi, float(value)))


def candidate_denoise_for(view: str, base: float, *, index: int = 0) -> float:
    """High enough denoise that pose/view can move; outfit locked by prompt/negative."""
    v = (view or "").lower()
    boost = 0.20
    if any(
        k in v
        for k in (
            "walk",
            "bow",
            "wave",
            "point",
            "cross",
            "three quarter",
            "side",
            "profile",
            "turn",
        )
    ):
        boost = 0.28
    elif any(k in v for k in ("hip", "clasp", "greeting")):
        boost = 0.24
    jitter = ((index % 5) - 2) * 0.02
    return clamp_denoise(base + boost + jitter, lo=0.70, hi=0.88)


def sheet_denoise_for(slot_key: str, base: float) -> float:
    """Per-slot denoise: side/back need near-txt2img to leave front composition."""
    key = (slot_key or "").lower()
    if key == "turnaround_back":
        return clamp_denoise(0.93, lo=0.88, hi=0.96)
    if key == "turnaround_side":
        return clamp_denoise(0.90, lo=0.88, hi=0.96)
    if key.startswith("expr_"):
        # Face crop already; keep moderate denoise for expression only.
        return clamp_denoise(base + 0.05, lo=0.45, hi=0.68)
    return clamp_denoise(base, lo=0.40, hi=0.75)


def sheet_cfg_for(slot_key: str) -> float:
    """Higher CFG so view/expression prompts beat look-lock latent."""
    key = (slot_key or "").lower()
    if key in {"turnaround_side", "turnaround_back"}:
        return 9.5
    if key.startswith("expr_"):
        return 8.0
    return 7.0


def candidate_cfg_for() -> float:
    return 8.5


def sheet_uses_look_lock_image(slot_key: str) -> bool:
    """All sheet slots can use look-lock; side/back use high denoise instead of skipping."""
    return bool(slot_key)


def look_lock_dir(vpaths: VisualPaths, character_id: str) -> Path:
    return vpaths.character_dir(character_id) / "look_lock"


def look_lock_ref_path(vpaths: VisualPaths, character_id: str) -> Path | None:
    ref = look_lock_dir(vpaths, character_id) / "ref.png"
    return ref if ref.exists() else None


def look_lock_face_ref_path(vpaths: VisualPaths, character_id: str) -> Path | None:
    ref = look_lock_dir(vpaths, character_id) / "face_ref.png"
    return ref if ref.exists() else None


def _write_face_crop(src: Path, dest: Path) -> Path:
    """Crop top-center head region from a full-body look-lock for expression img2img."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pillow_required_for_face_crop") from exc

    im = Image.open(src).convert("RGB")
    w, h = im.size
    # Anime full-body: head usually sits in the top ~35–40%.
    crop_h = max(64, int(h * 0.40))
    crop_w = max(64, int(min(w * 0.58, crop_h * 1.05)))
    left = max(0, (w - crop_w) // 2)
    top = max(0, int(h * 0.02))
    right = min(w, left + crop_w)
    bottom = min(h, top + crop_h)
    face = im.crop((left, top, right, bottom))
    side = max(face.size)
    canvas = Image.new("RGB", (side, side), (248, 248, 248))
    ox = (side - face.size[0]) // 2
    oy = (side - face.size[1]) // 2
    canvas.paste(face, (ox, oy))
    canvas = canvas.resize((768, 768), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="PNG")
    return dest


def ensure_face_ref(
    vpaths: VisualPaths,
    character_id: str,
    src: Path | None = None,
) -> Path:
    """Ensure look_lock/face_ref.png exists (regenerate if missing or stale)."""
    src = src or look_lock_ref_path(vpaths, character_id)
    if src is None or not src.exists():
        raise FileNotFoundError(f"look_lock_ref_missing:{character_id}")
    dest = look_lock_dir(vpaths, character_id) / "face_ref.png"
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest
    return _write_face_crop(src, dest)


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
    _write_face_crop(dest, dest_dir / "face_ref.png")

    strength = clamp_denoise(denoise, lo=0.40, hi=0.82)
    profile["look_lock"] = {
        "folder": folder,
        "file": filename,
        "ref_file": "ref.png",
        "face_ref_file": "face_ref.png",
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
    # Old default 0.48 was overly sticky; lift only that legacy value.
    if abs(denoise - 0.48) < 1e-6:
        denoise = DEFAULT_LOOK_LOCK_DENOISE
    return ref, clamp_denoise(denoise, lo=0.40, hi=0.82)
