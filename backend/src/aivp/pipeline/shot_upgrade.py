from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_text(v) for v in value if _text(v))
    return str(value).strip()


def upgrade_shot_to_v2(shot: dict, global_order: int = 1) -> dict:
    """Upgrade v1 shot fields into production shot schema v2 (backward compatible)."""
    out = dict(shot)
    order = int(out.get("order") or global_order or 1)
    episode = _text(out.get("episode")) or "EP001"
    scene = _text(out.get("scene")) or (
        f"SC{_text(out.get('chapter_id') or '001').replace('ch', '').zfill(3)}"
    )
    shot_num = f"SH{order:03d}"
    shot_id = _text(out.get("shot_id"))
    if not shot_id.startswith("EP") or "_SC" not in shot_id:
        shot_id = f"{episode}_{scene}_{shot_num}"
    out["shot_id"] = shot_id
    out["episode"] = episode
    out["scene"] = scene
    out["order"] = order
    out["global_order"] = int(out.get("global_order") or global_order)
    out["duration"] = float(out.get("duration") or out.get("duration_sec") or 4)
    out["duration_sec"] = int(round(out["duration"]))
    out["aspect_ratio"] = _text(out.get("aspect_ratio")) or "16:9"
    out["resolution"] = _text(out.get("resolution")) or "1344x768"
    out["location"] = _text(out.get("location") or out.get("location_name"))
    out["location_name"] = out["location"]
    out["time"] = _text(out.get("time")) or "未知"
    out["weather"] = _text(out.get("weather")) or ""
    characters = out.get("characters")
    if not isinstance(characters, list):
        characters = out.get("cast") if isinstance(out.get("cast"), list) else []
    characters = [_text(c) for c in characters if _text(c)]
    out["characters"] = characters
    out["cast"] = characters

    camera = out.get("camera")
    if isinstance(camera, str) or camera is None:
        out["camera"] = {
            "shot_size": _text(out.get("shot_type")) or "medium",
            "angle": "eye level",
            "movement": "static",
            "lens": "50mm",
            "composition": "centered, cinematic",
            "notes": _text(camera),
        }
    elif isinstance(camera, dict):
        out["camera"] = {
            "shot_size": _text(camera.get("shot_size") or out.get("shot_type")) or "medium",
            "angle": _text(camera.get("angle")) or "eye level",
            "movement": _text(camera.get("movement")) or "static",
            "lens": _text(camera.get("lens")) or "50mm",
            "composition": _text(camera.get("composition")) or "centered, cinematic",
            "notes": _text(camera.get("notes")),
        }

    out["action"] = _text(out.get("action"))
    out["emotion"] = _text(out.get("emotion") or out.get("audio_notes"))
    out["dialogue"] = out.get("dialogue") if out.get("dialogue") not in ("", None) else None
    out["voiceover"] = out.get("voiceover") if out.get("voiceover") not in ("", None) else None
    out["visual_prompt"] = _text(out.get("visual_prompt") or out.get("action"))
    out["audio_notes"] = _text(out.get("audio_notes"))
    out["shot_type"] = _text(out.get("shot_type") or out["camera"].get("shot_size")) or "medium"

    assets = out.get("assets_required")
    if not isinstance(assets, dict):
        assets = {}
    out["assets_required"] = {
        "characters": assets.get("characters")
        if isinstance(assets.get("characters"), list)
        else list(characters),
        "locations": assets.get("locations")
        if isinstance(assets.get("locations"), list)
        else ([out["location"]] if out["location"] else []),
        "props": assets.get("props") if isinstance(assets.get("props"), list) else [],
        "style": assets.get("style")
        if isinstance(assets.get("style"), list)
        else ["暗黑国风动画"],
    }

    gen = out.get("generation") if isinstance(out.get("generation"), dict) else {}
    out["generation"] = {
        "first_frame_required": bool(gen.get("first_frame_required", True)),
        "last_frame_required": bool(gen.get("last_frame_required", False)),
        "mode": _text(gen.get("mode")) or "image_to_video",
        "target_fps": int(gen.get("target_fps") or 24),
        "candidates": int(gen.get("candidates") or 4),
        "difficulty": _text(gen.get("difficulty")) or "medium",
    }

    review = out.get("review") if isinstance(out.get("review"), dict) else {}
    out["review"] = {
        "status": _text(review.get("status")) or "needs_review",
        "notes": review.get("notes") if isinstance(review.get("notes"), list) else [],
    }
    return out


def upgrade_shot_document(doc: dict) -> dict:
    shots = [upgrade_shot_to_v2(s, i) for i, s in enumerate(doc.get("shots") or [], start=1)]
    out = dict(doc)
    out["schema_version"] = 2
    out["shots"] = shots
    out["shot_count"] = len(shots)
    return out


def write_shot_yamls(shots_root: Path, shots: list[dict]) -> list[Path]:
    try:
        import yaml  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pyyaml_required") from e

    written: list[Path] = []
    for shot in shots:
        episode = _text(shot.get("episode")) or "EP001"
        scene = _text(shot.get("scene")) or "SC001"
        order = int(shot.get("order") or 1)
        filename = f"SH{order:03d}.yaml"
        dest = shots_root / episode / scene / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            yaml.safe_dump(shot, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        written.append(dest)
    return written


def build_asset_plan(shots: list[dict], *, approved_only: bool = False) -> dict:
    characters: dict[str, dict] = {}
    locations: dict[str, dict] = {}
    props: dict[str, dict] = {}
    for shot in shots:
        status = ((shot.get("review") or {}) if isinstance(shot.get("review"), dict) else {}).get(
            "status"
        )
        if approved_only and status not in ("approved", "locked"):
            continue
        sid = _text(shot.get("shot_id"))
        assets = shot.get("assets_required") if isinstance(shot.get("assets_required"), dict) else {}
        for name in assets.get("characters") or shot.get("characters") or shot.get("cast") or []:
            name = _text(name)
            if not name:
                continue
            entry = characters.setdefault(
                name,
                {
                    "name": name,
                    "shot_count": 0,
                    "priority": "medium",
                    "needs_lora": False,
                    "versions": [],
                    "source_shots": [],
                },
            )
            entry["shot_count"] += 1
            if sid and sid not in entry["source_shots"]:
                entry["source_shots"].append(sid)
        for name in assets.get("locations") or (
            [_text(shot.get("location") or shot.get("location_name"))]
        ):
            name = _text(name)
            if not name:
                continue
            entry = locations.setdefault(
                name,
                {
                    "name": name,
                    "shot_count": 0,
                    "priority": "medium",
                    "needs_reference_set": False,
                    "source_shots": [],
                },
            )
            entry["shot_count"] += 1
            if sid and sid not in entry["source_shots"]:
                entry["source_shots"].append(sid)
        for name in assets.get("props") or []:
            name = _text(name)
            if not name:
                continue
            entry = props.setdefault(
                name,
                {"name": name, "shot_count": 0, "priority": "low", "source_shots": []},
            )
            entry["shot_count"] += 1
            if sid and sid not in entry["source_shots"]:
                entry["source_shots"].append(sid)

    for entry in characters.values():
        if entry["shot_count"] >= 8:
            entry["priority"] = "high"
            entry["needs_lora"] = True
        elif entry["shot_count"] >= 3:
            entry["priority"] = "medium"
    for entry in locations.values():
        if entry["shot_count"] >= 5:
            entry["priority"] = "high"
            entry["needs_reference_set"] = True

    return {
        "characters": sorted(characters.values(), key=lambda x: -x["shot_count"]),
        "locations": sorted(locations.values(), key=lambda x: -x["shot_count"]),
        "props": sorted(props.values(), key=lambda x: -x["shot_count"]),
        "style": [{"name": "暗黑国风动画", "priority": "high"}],
    }


def save_asset_plan(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
