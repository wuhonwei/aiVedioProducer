"""Curate location plates into curated/ for LoRA training."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from typing import Any

from aivp.visual.location_profiles import save_location_profile
from aivp.visual.paths import VisualPaths


def curate_location_images(
    vpaths: VisualPaths,
    location_id: str,
    keep: list[str],
    *,
    keep_sheets: list[str] | None = None,
) -> dict[str, Any]:
    vpaths.ensure_location(location_id)
    cand_dir = vpaths.location_candidates_dir(location_id)
    sheets_dir = vpaths.location_sheets_dir(location_id)
    curated_dir = vpaths.location_curated_dir(location_id)
    for old in curated_dir.glob("*"):
        if old.is_file():
            old.unlink()

    profile_path = vpaths.location_profile_json(location_id)
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    trigger = str(profile.get("trigger") or "")
    look = (profile.get("prompt_zh") or "").strip()
    saved: list[str] = []
    sources: list[dict[str, str]] = []

    def _ensure_caption(dest, *, tag: str) -> None:
        cap = dest.with_suffix(".txt")
        if cap.exists():
            text = cap.read_text(encoding="utf-8").strip()
            if trigger and trigger not in text:
                text = f"{trigger}, {text}"
                cap.write_text(text, encoding="utf-8")
            return
        parts = [
            trigger,
            look,
            tag,
            "empty scene",
            "no people",
            "guofeng location plate",
        ]
        cap.write_text(", ".join(p for p in parts if p), encoding="utf-8")

    for name in keep or []:
        src = cand_dir / name
        if not src.exists() or src.suffix.lower() != ".png":
            continue
        dest = curated_dir / name
        shutil.copy2(src, dest)
        cap_src = src.with_suffix(".txt")
        if cap_src.exists():
            shutil.copy2(cap_src, dest.with_suffix(".txt"))
        _ensure_caption(dest, tag="empty establishing location plate")
        saved.append(name)
        sources.append({"folder": "candidates", "file": name})

    for name in keep_sheets or []:
        src = sheets_dir / name
        if not src.exists() or src.suffix.lower() != ".png":
            continue
        dest = curated_dir / name
        shutil.copy2(src, dest)
        cap_src = src.with_suffix(".txt")
        if cap_src.exists():
            shutil.copy2(cap_src, dest.with_suffix(".txt"))
        _ensure_caption(dest, tag="empty location environment sheet")
        saved.append(name)
        sources.append({"folder": "sheets", "file": name})

    if saved:
        profile["status"] = "curated_ready"
        profile["train_status"] = "curated_ready"
    else:
        profile["train_status"] = profile.get("train_status", "not_started")
    profile["curated_at"] = datetime.now(timezone.utc).isoformat()
    profile["curated_files"] = saved
    profile["curated_sources"] = sources
    profile["location_id"] = location_id
    save_location_profile(vpaths, profile)
    return {
        "location_id": location_id,
        "curated": saved,
        "count": len(saved),
        "sources": sources,
        "train_status": profile.get("train_status"),
    }
