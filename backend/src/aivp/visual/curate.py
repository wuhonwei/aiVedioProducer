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
) -> dict[str, Any]:
    vpaths.ensure_character(character_id)
    cand_dir = vpaths.candidates_dir(character_id)
    curated_dir = vpaths.curated_dir(character_id)
    # Clear previous curated images (keep folder).
    for old in curated_dir.glob("*"):
        if old.is_file():
            old.unlink()
    saved: list[str] = []
    for name in keep:
        src = cand_dir / name
        if not src.exists() or src.suffix.lower() != ".png":
            continue
        dest = curated_dir / name
        shutil.copy2(src, dest)
        cap_src = src.with_suffix(".txt")
        if cap_src.exists():
            shutil.copy2(cap_src, dest.with_suffix(".txt"))
        saved.append(name)

    profile_path = vpaths.profile_json(character_id)
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    profile["status"] = "curated" if saved else profile.get("status", "profiled")
    profile["curated_at"] = datetime.now(timezone.utc).isoformat()
    profile["curated_files"] = saved
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"character_id": character_id, "curated": saved, "count": len(saved)}
