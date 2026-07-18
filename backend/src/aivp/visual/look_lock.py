from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import read_profile_json, save_profile

LOOK_LOCK_FOLDERS = frozenset(
    {"candidates", "sheets", "generations", "curated", "look_lock_archive"}
)
# Base for front / soft identity; view/pose slots use higher denoise on top.
DEFAULT_LOOK_LOCK_DENOISE = 0.55


def clamp_denoise(value: float, *, lo: float = 0.40, hi: float = 0.96) -> float:
    return max(lo, min(hi, float(value)))


def candidate_denoise_for(
    view: str,
    base: float,
    *,
    index: int = 0,
    tuning: dict | None = None,
    ref_kind: str = "full",
) -> float:
    """Balance pose change vs outfit lock; too-high denoise rewrites clothes.

    Full-body look-lock refs must stay in a lower denoise band so costume sticks.
    ``ref_kind="face"`` (sheets/expr) may sit higher.
    """
    tun = tuning or {}
    if (ref_kind or "full").lower() == "face":
        lo = float(tun.get("candidate_denoise_lo") or 0.72)
        hi = float(tun.get("candidate_denoise_hi") or 0.88)
        hi = max(hi, 0.78)
        lo = min(lo, hi - 0.02)
        boost = 0.14
    else:
        # Full ref: prioritize outfit lock; only mild stance / camera drift.
        lo = float(tun.get("candidate_denoise_lo") or 0.52)
        hi = float(tun.get("candidate_denoise_hi") or 0.66)
        hi = min(hi, 0.70)
        lo = min(lo, hi - 0.02)
        boost = 0.06
    v = (view or "").lower()
    if (ref_kind or "full").lower() != "face":
        if any(k in v for k in ("three quarter", "turn", "contrapposto", "side")):
            boost = 0.08
        elif any(k in v for k in ("walk", "wave", "bow", "point", "cross", "hip")):
            # Aggressive actions fight the lock photo — keep denoise low.
            boost = 0.04
    else:
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
            boost = 0.18
        elif any(k in v for k in ("hip", "clasp", "greeting")):
            boost = 0.15
    jitter = ((index % 5) - 2) * 0.01
    return clamp_denoise(base + boost + jitter, lo=lo, hi=hi)


def sheet_denoise_for(slot_key: str, base: float, *, tuning: dict | None = None) -> float:
    """Per-slot denoise: side/back need near-txt2img to leave front composition."""
    tun = tuning or {}
    key = (slot_key or "").lower()
    if key == "turnaround_back":
        return clamp_denoise(float(tun.get("back_denoise") or 0.93), lo=0.88, hi=0.96)
    if key == "turnaround_side":
        return clamp_denoise(float(tun.get("side_denoise") or 0.90), lo=0.88, hi=0.96)
    if key.startswith("expr_"):
        # Face_ref locks identity; denoise must be high enough for mouth/eyes/brows
        # to leave the locked calm face (low values make all exprs look identical).
        # Strong emotions need extra denoise vs calm/smile.
        per_slot = {
            "expr_calm": 0.68,
            "expr_smile": 0.74,
            "expr_shy": 0.76,
            "expr_happy": 0.80,
            # Strong emotions: keep face_ref for framing, push denoise near-txt2img.
            "expr_confused": 0.90,
            "expr_sad": 0.92,
            "expr_angry": 0.94,
            "expr_surprised": 0.94,
        }
        default = max(float(base) + 0.18, float(per_slot.get(key, 0.74)))
        tuned = tun.get("expr_denoise")
        value = default if tuned is None else max(float(tuned), default)
        return clamp_denoise(value, lo=0.62, hi=0.96)
    return clamp_denoise(base, lo=0.40, hi=0.75)


def sheet_uses_look_lock_image(slot_key: str) -> bool:
    """Front/expr can img2img; side/back must be txt2img or front pose sticks."""
    key = (slot_key or "").lower()
    return key not in {"turnaround_side", "turnaround_back"}


def sheet_cfg_for(slot_key: str, *, tuning: dict | None = None) -> float:
    """Higher CFG so view/expression prompts beat look-lock latent / priors."""
    tun = tuning or {}
    key = (slot_key or "").lower()
    if key in {"turnaround_side", "turnaround_back"}:
        return float(tun.get("side_back_cfg") or 12.5)
    if key.startswith("expr_"):
        tuned = float(tun["expr_cfg"]) if tun.get("expr_cfg") is not None else None
        if key in {"expr_angry", "expr_surprised", "expr_sad", "expr_confused"}:
            return max(tuned if tuned is not None else 12.5, 12.5)
        return tuned if tuned is not None else 11.0
    return 7.0


def candidate_cfg_for(*, ref_kind: str = "full") -> float:
    # Face-ref candidates need stronger prompt pull so action + wardrobe beat the
    # headshot latent (especially the blank lower body).
    if (ref_kind or "full").lower() == "face":
        return 10.5
    return 8.5


def look_lock_dir(vpaths: VisualPaths, character_id: str) -> Path:
    return vpaths.character_dir(character_id) / "look_lock"


def look_lock_ref_path(vpaths: VisualPaths, character_id: str) -> Path | None:
    ref = look_lock_dir(vpaths, character_id) / "ref.png"
    return ref if ref.exists() else None


def look_lock_face_ref_path(vpaths: VisualPaths, character_id: str) -> Path | None:
    ref = look_lock_dir(vpaths, character_id) / "face_ref.png"
    return ref if ref.exists() else None


def _write_face_crop(src: Path, dest: Path) -> Path:
    """Build a square headshot ref for expression img2img.

    Candidate / look-lock refs are often tall upper-body portraits (e.g. 768×1024).
    Padding those to a square leaves gray side bars and a tiny face — expression
    img2img then copies that composition. Always extract a top-center square so
    forehead→chin fills most of the canvas.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pillow_required_for_face_crop") from exc

    im = Image.open(src).convert("RGB")
    w, h = im.size
    aspect = w / max(h, 1)

    if aspect >= 0.95:
        # Near-square: slight upper zoom so medium shots become headshots.
        side = min(w, h)
        zoom = max(64, int(side * 0.78))
        left = max(0, (w - zoom) // 2)
        top = max(0, int(h * 0.03))
        if top + zoom > h:
            top = max(0, h - zoom)
        face = im.crop((left, top, left + zoom, top + zoom))
        canvas = face
    elif aspect >= 0.55:
        # Portrait / upper-body (incl. 3:4): tight top-center square — no side pad.
        # ~48% of height ≈ forehead→chin with bun + slight shoulder; not chest shot.
        side = min(w, max(64, int(h * 0.48)))
        side = min(side, max(64, int(w * 0.85)))
        left = max(0, (w - side) // 2)
        top = max(0, int(h * 0.015))
        if top + side > h:
            top = max(0, h - side)
        face = im.crop((left, top, left + side, top + side))
        canvas = face
    else:
        # Very tall full-body: take a wide top band, then pad to square if needed.
        crop_h = max(64, int(h * 0.42))
        crop_w = max(64, int(min(w * 0.88, crop_h * 1.05)))
        left = max(0, (w - crop_w) // 2)
        top = max(0, int(h * 0.01))
        right = min(w, left + crop_w)
        bottom = min(h, top + crop_h)
        face = im.crop((left, top, right, bottom))
        side = max(face.size)
        canvas = Image.new("RGB", (side, side), (248, 248, 248))
        canvas.paste(face, ((side - face.size[0]) // 2, (side - face.size[1]) // 2))

    canvas = canvas.resize((768, 768), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="PNG")
    return dest


def ensure_face_ref(
    vpaths: VisualPaths,
    character_id: str,
    src: Path | None = None,
) -> Path:
    """Ensure look_lock/face_ref.png exists (always refresh from current ref)."""
    src = src or look_lock_ref_path(vpaths, character_id)
    if src is None or not src.exists():
        raise FileNotFoundError(f"look_lock_ref_missing:{character_id}")
    dest = look_lock_dir(vpaths, character_id) / "face_ref.png"
    return _write_face_crop(src, dest)


def ensure_candidate_face_ref(
    vpaths: VisualPaths,
    character_id: str,
    src: Path | None = None,
) -> Path:
    """Build a 768×1024 canvas with face on top and neutral lower body.

    Full-body look-lock ``ref.png`` pins pose under img2img. Stretching a square
    face crop to 3:4 also imprints a weird prior. Paste the headshot in the upper
    band and leave the torso/legs as neutral fill so denoise can invent new poses
    while identity stays anchored to the face.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pillow_required_for_face_crop") from exc

    face_path = ensure_face_ref(vpaths, character_id, src)
    face = Image.open(face_path).convert("RGB")
    w, h = 768, 1024
    canvas = Image.new("RGB", (w, h), (236, 232, 224))
    # Upper ~42% holds the face; leave room for full-body generation below.
    face_h = max(256, int(h * 0.42))
    face_w = max(256, int(min(w * 0.88, face_h)))
    face_resized = face.resize((face_w, face_h), Image.Resampling.LANCZOS)
    left = (w - face_w) // 2
    top = max(0, int(h * 0.02))
    canvas.paste(face_resized, (left, top))
    dest = look_lock_dir(vpaths, character_id) / "candidate_face_ref.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="PNG")
    return dest


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

    profile = read_profile_json(vpaths.profile_json(character_id))
    if profile is None:
        raise FileNotFoundError(f"profile_missing:{character_id}")

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
    profile = read_profile_json(vpaths.profile_json(character_id))
    if profile is None:
        raise FileNotFoundError(f"profile_missing:{character_id}")
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
        profile = read_profile_json(vpaths.profile_json(character_id))
        if profile is None:
            return None, 1.0
    lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
    ref = look_lock_ref_path(vpaths, character_id)
    if not lock or not ref:
        return None, 1.0
    denoise = float(lock.get("denoise") or DEFAULT_LOOK_LOCK_DENOISE)
    # Old default 0.48 was overly sticky; lift only that legacy value.
    if abs(denoise - 0.48) < 1e-6:
        denoise = DEFAULT_LOOK_LOCK_DENOISE
    return ref, clamp_denoise(denoise, lo=0.40, hi=0.82)
