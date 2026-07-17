from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Re-export asset plan helpers for backward-compatible imports.
from aivp.pipeline.asset_plan import (  # noqa: F401
    build_asset_plan,
    patch_asset_plan_entry,
    save_asset_plan,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_text(v) for v in value if _text(v))
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(x) for x in value if _text(x)]


def _shot_review_status(shot: dict) -> str:
    top = _text(shot.get("review_status"))
    if top:
        return top
    review = shot.get("review") if isinstance(shot.get("review"), dict) else {}
    return _text(review.get("status")) or "needs_review"


def is_shot_approved(shot: dict) -> bool:
    status = _shot_review_status(shot)
    return bool(shot.get("locked")) or status in ("approved", "locked")


def upgrade_shot_to_v2(
    shot: dict,
    global_order: int = 1,
    *,
    name_to_id: dict[str, str] | None = None,
) -> dict:
    """Upgrade v1 shot fields into production shot schema v2 (backward compatible)."""
    out = dict(shot)
    order = int(out.get("order") or global_order or 1)
    episode = _text(out.get("episode_id") or out.get("episode")) or "EP001"
    scene = _text(out.get("scene_id") or out.get("scene")) or (
        f"SC{_text(out.get('chapter_id') or '001').replace('ch', '').replace('chapter_', '').zfill(3)}"
    )
    shot_num = f"SH{order:03d}"
    shot_id = _text(out.get("shot_id"))
    if not shot_id.startswith("EP") or "_SC" not in shot_id:
        shot_id = f"{episode}_{scene}_{shot_num}"
    out["shot_id"] = shot_id
    out["episode"] = episode
    out["scene"] = scene
    out["episode_id"] = episode
    out["scene_id"] = scene
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
            "movement": _text(out.get("camera_movement")) or "static",
            "lens": _text(out.get("lens")) or "50mm",
            "composition": _text(out.get("composition")) or "centered, cinematic",
            "notes": _text(camera),
        }
    elif isinstance(camera, dict):
        out["camera"] = {
            "shot_size": _text(camera.get("shot_size") or out.get("shot_type")) or "medium",
            "angle": _text(camera.get("angle")) or "eye level",
            "movement": _text(
                camera.get("movement") or out.get("camera_movement")
            )
            or "static",
            "lens": _text(camera.get("lens") or out.get("lens")) or "50mm",
            "composition": _text(camera.get("composition") or out.get("composition"))
            or "centered, cinematic",
            "notes": _text(camera.get("notes")),
        }

    out["camera_movement"] = out["camera"]["movement"]
    out["lens"] = out["camera"]["lens"]
    out["composition"] = out["camera"]["composition"]

    out["action"] = _text(out.get("action"))
    out["emotion"] = _text(out.get("emotion") or out.get("audio_notes"))
    out["dialogue"] = out.get("dialogue") if out.get("dialogue") not in ("", None) else None
    out["voiceover"] = out.get("voiceover") if out.get("voiceover") not in ("", None) else None
    out["visual_prompt"] = _text(out.get("visual_prompt") or out.get("action"))
    out["negative_prompt"] = _text(out.get("negative_prompt"))
    out["audio_notes"] = _text(out.get("audio_notes"))
    out["shot_type"] = _text(out.get("shot_type") or out["camera"].get("shot_size")) or "medium"

    assets = out.get("assets_required")
    if not isinstance(assets, dict):
        assets = {}
    props = _as_str_list(assets.get("props") if assets.get("props") is not None else out.get("props"))
    out["props"] = props
    out["assets_required"] = {
        "characters": assets.get("characters")
        if isinstance(assets.get("characters"), list)
        else list(characters),
        "locations": assets.get("locations")
        if isinstance(assets.get("locations"), list)
        else ([out["location"]] if out["location"] else []),
        "props": props,
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
    out["generation_status"] = _text(out.get("generation_status")) or "not_started"

    review = out.get("review") if isinstance(out.get("review"), dict) else {}
    status = _text(out.get("review_status") or review.get("status")) or "needs_review"
    locked = bool(out.get("locked")) or status == "locked"
    if locked and status != "locked":
        status = "locked"
    out["review"] = {
        "status": status,
        "notes": review.get("notes") if isinstance(review.get("notes"), list) else [],
    }
    out["review_status"] = status
    out["locked"] = locked

    # Resolve ids from name map when available.
    n2i = name_to_id or {}
    location_id = _text(out.get("location_id"))
    if not location_id and out["location"] and out["location"] in n2i:
        location_id = n2i[out["location"]]
    out["location_id"] = location_id

    char_ids: list[str] = []
    for name in out["assets_required"]["characters"] or characters:
        key = _text(name)
        if not key:
            continue
        char_ids.append(n2i.get(key) or key)
    loc_ids: list[str] = []
    for name in out["assets_required"]["locations"] or (
        [out["location"]] if out["location"] else []
    ):
        key = _text(name)
        if not key:
            continue
        loc_ids.append(n2i.get(key) or key)
    prop_ids: list[str] = []
    for name in props:
        key = _text(name)
        if not key:
            continue
        prop_ids.append(n2i.get(key) or key)

    existing_refs = out.get("asset_refs") if isinstance(out.get("asset_refs"), dict) else {}
    out["asset_refs"] = {
        "characters": _as_str_list(existing_refs.get("characters")) or char_ids,
        "locations": _as_str_list(existing_refs.get("locations")) or loc_ids,
        "props": _as_str_list(existing_refs.get("props")) or prop_ids,
    }

    source_refs = out.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        evidence = _text(out.get("evidence") or out.get("action") or out.get("visual_prompt"))
        source_refs = [
            {
                "chapter_id": _text(out.get("chapter_id")),
                "chunk_id": _text(out.get("chunk_id")),
                "event_id": _text(out.get("event_id")),
                "evidence": evidence,
            }
        ]
    else:
        normalized = []
        for ref in source_refs:
            if not isinstance(ref, dict):
                continue
            normalized.append(
                {
                    "chapter_id": _text(ref.get("chapter_id") or out.get("chapter_id")),
                    "chunk_id": _text(ref.get("chunk_id") or out.get("chunk_id")),
                    "event_id": _text(ref.get("event_id") or out.get("event_id")),
                    "evidence": _text(ref.get("evidence") or out.get("action")),
                }
            )
        source_refs = normalized or [
            {
                "chapter_id": _text(out.get("chapter_id")),
                "chunk_id": _text(out.get("chunk_id")),
                "event_id": _text(out.get("event_id")),
                "evidence": _text(out.get("action")),
            }
        ]
    out["source_refs"] = source_refs
    return out


def build_name_to_id_map(assets: dict | None = None, entities: dict | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source in (assets, entities):
        if not isinstance(source, dict):
            continue
        for kind in ("characters", "locations", "props", "factions"):
            for item in source.get(kind) or []:
                if not isinstance(item, dict):
                    continue
                eid = _text(item.get("id"))
                name = _text(item.get("canonical_name") or item.get("name"))
                if name and eid:
                    mapping[name] = eid
                for alias in item.get("aliases") or []:
                    a = _text(alias)
                    if a and eid:
                        mapping[a] = eid
    return mapping


def upgrade_shot_document(
    doc: dict,
    *,
    name_to_id: dict[str, str] | None = None,
) -> dict:
    shots = [
        upgrade_shot_to_v2(s, i, name_to_id=name_to_id)
        for i, s in enumerate(doc.get("shots") or [], start=1)
    ]
    out = dict(doc)
    out["schema_version"] = 2
    out["shots"] = shots
    out["shot_count"] = len(shots)
    return out


def write_shot_yamls(
    shots_root: Path,
    shots: list[dict],
    *,
    approved_only: bool = False,
) -> list[Path]:
    try:
        import yaml  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pyyaml_required") from e

    written: list[Path] = []
    for shot in shots:
        if approved_only and not is_shot_approved(shot):
            continue
        episode = _text(shot.get("episode_id") or shot.get("episode")) or "EP001"
        scene = _text(shot.get("scene_id") or shot.get("scene")) or "SC001"
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


def build_shot_script_index(doc: dict) -> dict:
    shots = list(doc.get("shots") or [])
    by_chapter: dict[str, list[str]] = {}
    by_event: dict[str, list[str]] = {}
    for shot in shots:
        sid = _text(shot.get("shot_id"))
        if not sid:
            continue
        chapter_id = _text(shot.get("chapter_id")) or "unknown"
        event_id = _text(shot.get("event_id")) or "unknown"
        by_chapter.setdefault(chapter_id, []).append(sid)
        by_event.setdefault(event_id, []).append(sid)
    return {
        "schema_version": 2,
        "generated_at": _text(doc.get("generated_at"))
        or datetime.now(timezone.utc).isoformat(),
        "event_count": int(doc.get("event_count") or len(by_event)),
        "shot_count": len(shots),
        "chapters": [
            {"chapter_id": cid, "shot_ids": ids, "shot_count": len(ids)}
            for cid, ids in sorted(by_chapter.items())
        ],
        "events": [
            {"event_id": eid, "shot_ids": ids, "shot_count": len(ids)}
            for eid, ids in sorted(by_event.items())
        ],
        "volumes": list(doc.get("volumes") or []),
        "path": "shot_script.json",
        "warnings": list(doc.get("warnings") or []),
    }


def write_shot_script_index(path: Path, doc: dict) -> dict:
    index = build_shot_script_index(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index
