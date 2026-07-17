from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_text(v) for v in value if _text(v))
    return str(value).strip()


def _review_status(shot: dict) -> str:
    top = _text(shot.get("review_status"))
    if top:
        return top
    review = shot.get("review") if isinstance(shot.get("review"), dict) else {}
    return _text(review.get("status")) or "needs_review"


def _is_approved(shot: dict) -> bool:
    status = _review_status(shot)
    return bool(shot.get("locked")) or status in ("approved", "locked")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _name_to_id(entities: dict | None, assets: dict | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source in (entities, assets):
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


def _priority_for(shot_count: int, score: float, *, high_at: int, mid_at: int) -> str:
    if shot_count >= high_at or score >= 0.85:
        return "high"
    if shot_count >= mid_at or score >= 0.55:
        return "medium"
    return "low"


def build_asset_plan(
    shots: list[dict],
    *,
    approved_only: bool = True,
    entities: dict | None = None,
    assets: dict | None = None,
) -> dict:
    """Aggregate characters/locations/props from shots into a production asset plan."""
    n2i = _name_to_id(entities, assets)
    characters: dict[str, dict] = {}
    locations: dict[str, dict] = {}
    props: dict[str, dict] = {}
    used = 0

    for shot in shots:
        if approved_only and not _is_approved(shot):
            continue
        used += 1
        sid = _text(shot.get("shot_id"))
        assets_req = (
            shot.get("assets_required") if isinstance(shot.get("assets_required"), dict) else {}
        )
        score = max(
            _float(shot.get("importance")),
            _float(shot.get("visual_score")),
            max(
                (
                    _float(ref.get("importance"))
                    for ref in (shot.get("source_refs") or [])
                    if isinstance(ref, dict)
                ),
                default=0.0,
            ),
        )

        for name in assets_req.get("characters") or shot.get("characters") or shot.get("cast") or []:
            name = _text(name)
            if not name:
                continue
            eid = n2i.get(name) or f"char_{abs(hash(name)) % 10_000:04d}"
            entry = characters.setdefault(
                eid,
                {
                    "id": eid,
                    "name": name,
                    "shot_ids": [],
                    "source_shots": [],
                    "shot_count": 0,
                    "priority": "medium",
                    "needs_lora": False,
                    "status": "pending",
                    "versions": [],
                    "source_refs": [],
                    "_score": 0.0,
                },
            )
            entry["shot_count"] += 1
            entry["_score"] = max(float(entry.get("_score") or 0), score)
            if sid and sid not in entry["shot_ids"]:
                entry["shot_ids"].append(sid)
                entry["source_shots"].append(sid)

        for name in assets_req.get("locations") or (
            [_text(shot.get("location") or shot.get("location_name"))]
        ):
            name = _text(name)
            if not name:
                continue
            eid = _text(shot.get("location_id")) or n2i.get(name) or f"loc_{abs(hash(name)) % 10_000:04d}"
            entry = locations.setdefault(
                eid,
                {
                    "id": eid,
                    "name": name,
                    "shot_ids": [],
                    "source_shots": [],
                    "shot_count": 0,
                    "priority": "medium",
                    "needs_concept_art": False,
                    "needs_reference_set": False,
                    "status": "pending",
                    "description": "",
                    "source_refs": [],
                    "_score": 0.0,
                },
            )
            entry["shot_count"] += 1
            entry["_score"] = max(float(entry.get("_score") or 0), score)
            if sid and sid not in entry["shot_ids"]:
                entry["shot_ids"].append(sid)
                entry["source_shots"].append(sid)

        for name in assets_req.get("props") or shot.get("props") or []:
            name = _text(name)
            if not name:
                continue
            eid = n2i.get(name) or f"prop_{abs(hash(name)) % 10_000:04d}"
            entry = props.setdefault(
                eid,
                {
                    "id": eid,
                    "name": name,
                    "shot_ids": [],
                    "source_shots": [],
                    "shot_count": 0,
                    "priority": "low",
                    "needs_reference": False,
                    "status": "pending",
                    "source_refs": [],
                    "_score": 0.0,
                },
            )
            entry["shot_count"] += 1
            entry["_score"] = max(float(entry.get("_score") or 0), score)
            if sid and sid not in entry["shot_ids"]:
                entry["shot_ids"].append(sid)
                entry["source_shots"].append(sid)

    for entry in characters.values():
        entry["priority"] = _priority_for(
            entry["shot_count"], float(entry.pop("_score", 0)), high_at=8, mid_at=3
        )
        entry["needs_lora"] = entry["priority"] == "high" or entry["shot_count"] >= 5
    for entry in locations.values():
        entry["priority"] = _priority_for(
            entry["shot_count"], float(entry.pop("_score", 0)), high_at=5, mid_at=2
        )
        needs = entry["priority"] == "high" or entry["shot_count"] >= 3
        entry["needs_concept_art"] = needs
        entry["needs_reference_set"] = needs
    for entry in props.values():
        entry["priority"] = _priority_for(
            entry["shot_count"], float(entry.pop("_score", 0)), high_at=4, mid_at=2
        )
        entry["needs_reference"] = entry["priority"] in ("high", "medium")

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_from": {
            "shot_review_status": "approved_only" if approved_only else "all",
            "shot_count": used,
        },
        "characters": sorted(characters.values(), key=lambda x: -x["shot_count"]),
        "locations": sorted(locations.values(), key=lambda x: -x["shot_count"]),
        "props": sorted(props.values(), key=lambda x: -x["shot_count"]),
        "style": [{"name": "暗黑国风动画", "priority": "high", "status": "pending"}],
    }


def save_asset_plan(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def patch_asset_plan_entry(
    plan: dict,
    asset_type: str,
    asset_id: str,
    patch: dict[str, Any],
) -> dict:
    key = asset_type if asset_type.endswith("s") else asset_type + "s"
    if key not in ("characters", "locations", "props"):
        raise KeyError(f"unsupported_asset_type:{asset_type}")
    items = list(plan.get(key) or [])
    found = None
    for i, item in enumerate(items):
        if _text(item.get("id")) == asset_id or _text(item.get("name")) == asset_id:
            updated = dict(item)
            for field in (
                "status",
                "priority",
                "needs_lora",
                "needs_concept_art",
                "needs_reference",
                "needs_reference_set",
                "description",
                "appearance",
            ):
                if field in patch:
                    updated[field] = patch[field]
            # Keep mirrors in sync.
            if "needs_concept_art" in patch and "needs_reference_set" not in patch:
                updated["needs_reference_set"] = bool(patch["needs_concept_art"])
            if "needs_reference_set" in patch and "needs_concept_art" not in patch:
                updated["needs_concept_art"] = bool(patch["needs_reference_set"])
            items[i] = updated
            found = updated
            break
    if found is None:
        raise KeyError(f"asset_not_found:{asset_type}:{asset_id}")
    out = dict(plan)
    out[key] = items
    return out
