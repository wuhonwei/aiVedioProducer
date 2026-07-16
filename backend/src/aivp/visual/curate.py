from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from typing import Any

from aivp.visual.paths import VisualPaths


def curate_candidates(
    vpaths: VisualPaths,
    character_id: str,
    keep: list[str],
    *,
    keep_sheets: list[str] | None = None,
) -> dict[str, Any]:
    """Copy selected candidates and/or sheets into curated/ for LoRA training."""
    vpaths.ensure_character(character_id)
    cand_dir = vpaths.candidates_dir(character_id)
    sheets_dir = vpaths.sheets_dir(character_id)
    curated_dir = vpaths.curated_dir(character_id)
    for old in curated_dir.glob("*"):
        if old.is_file():
            old.unlink()

    saved: list[str] = []
    sources: list[dict[str, str]] = []

    for name in keep or []:
        src = cand_dir / name
        if not src.exists() or src.suffix.lower() != ".png":
            continue
        dest = curated_dir / name
        shutil.copy2(src, dest)
        cap_src = src.with_suffix(".txt")
        if cap_src.exists():
            shutil.copy2(cap_src, dest.with_suffix(".txt"))
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
        else:
            dest.with_suffix(".txt").write_text(
                f"character sheet, {name}",
                encoding="utf-8",
            )
        saved.append(name)
        sources.append({"folder": "sheets", "file": name})

    profile_path = vpaths.profile_json(character_id)
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    profile["status"] = "curated" if saved else profile.get("status", "profiled")
    profile["curated_at"] = datetime.now(timezone.utc).isoformat()
    profile["curated_files"] = saved
    profile["curated_sources"] = sources
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "character_id": character_id,
        "curated": saved,
        "count": len(saved),
        "sources": sources,
    }
