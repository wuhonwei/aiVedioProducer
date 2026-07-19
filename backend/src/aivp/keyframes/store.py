from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.keyframes.paths import KeyframePaths, safe_filename, safe_shot_id

_CANDIDATE_STEM_RE = re.compile(r"^kf_(\d+)$", re.IGNORECASE)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def list_candidates(kpaths: KeyframePaths, shot_id: str) -> list[dict[str, Any]]:
    safe_shot_id(shot_id)
    cand_dir = kpaths.candidates_dir(shot_id)
    if not cand_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for png in sorted(cand_dir.glob("*.png")):
        entry: dict[str, Any] = {"file": png.name}
        sidecar = png.with_suffix(".json")
        meta = _read_json(sidecar)
        if meta:
            entry.update(meta)
            entry["file"] = png.name
        out.append(entry)
    return out


def read_generation(kpaths: KeyframePaths, shot_id: str) -> dict[str, Any] | None:
    safe_shot_id(shot_id)
    return _read_json(kpaths.generation_json(shot_id))


def read_selected(kpaths: KeyframePaths, shot_id: str) -> dict[str, Any] | None:
    safe_shot_id(shot_id)
    return _read_json(kpaths.selected_json(shot_id))


def select_keyframe(
    kpaths: KeyframePaths,
    shot_id: str,
    filename: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    sid = safe_shot_id(shot_id)
    name = safe_filename(filename)
    png = kpaths.candidates_dir(sid) / name
    if not png.exists():
        raise ValueError(f"candidate_not_found:{name}")
    payload = {
        "shot_id": sid,
        "selected_file": name,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "approved",
        "note": note or "",
    }
    _write_json(kpaths.selected_json(sid), payload)
    return payload


def reject_keyframe(
    kpaths: KeyframePaths,
    shot_id: str,
    filename: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    sid = safe_shot_id(shot_id)
    name = safe_filename(filename)
    cleared_selection = False

    selected = read_selected(kpaths, sid)
    if selected and selected.get("selected_file") == name:
        sel_path = kpaths.selected_json(sid)
        if sel_path.exists():
            sel_path.unlink()
        cleared_selection = True

    review_path = kpaths.review_json(sid)
    review = _read_json(review_path) or {"events": []}
    events = list(review.get("events") or [])
    events.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "action": "reject",
            "filename": name,
            "reason": reason or "",
        }
    )
    review["events"] = events
    _write_json(review_path, review)

    sidecar = kpaths.candidates_dir(sid) / f"{Path(name).stem}.json"
    meta = _read_json(sidecar)
    if meta is not None:
        quality = dict(meta.get("quality") or {})
        quality["status"] = "rejected"
        meta["quality"] = quality
        _write_json(sidecar, meta)

    return {
        "filename": name,
        "cleared_selection": cleared_selection,
        "reason": reason or "",
    }


def delete_candidate(
    kpaths: KeyframePaths,
    shot_id: str,
    filename: str,
) -> dict[str, Any]:
    sid = safe_shot_id(shot_id)
    name = safe_filename(filename)
    cand_dir = kpaths.candidates_dir(sid)
    png = cand_dir / name
    sidecar = cand_dir / f"{Path(name).stem}.json"

    cleared_selection = False
    selected = read_selected(kpaths, sid)
    if selected and selected.get("selected_file") == name:
        sel_path = kpaths.selected_json(sid)
        if sel_path.exists():
            sel_path.unlink()
        cleared_selection = True

    removed = False
    if png.exists():
        png.unlink()
        removed = True
    if sidecar.exists():
        sidecar.unlink()
        removed = True

    return {
        "filename": name,
        "removed": removed,
        "cleared_selection": cleared_selection,
    }


def derive_status(kpaths: KeyframePaths, shot_id: str) -> str:
    safe_shot_id(shot_id)
    candidates = list_candidates(kpaths, shot_id)
    if not candidates:
        return "empty"

    selected = read_selected(kpaths, shot_id)
    if selected and selected.get("selected_file"):
        return "selected"

    review = _read_json(kpaths.review_json(shot_id))
    if review and review.get("events"):
        return "rejected"

    return "candidates"


def next_candidate_stem(kpaths: KeyframePaths, shot_id: str) -> str:
    safe_shot_id(shot_id)
    cand_dir = kpaths.candidates_dir(shot_id)
    max_idx = 0
    if cand_dir.exists():
        for png in cand_dir.glob("*.png"):
            m = _CANDIDATE_STEM_RE.match(png.stem)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
    return f"kf_{max_idx + 1:04d}"
