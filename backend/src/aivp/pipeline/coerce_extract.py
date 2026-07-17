from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_text(v) for v in value]
        return " ".join(p for p in parts if p).strip()
    return str(value).strip()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aliases(item: dict[str, Any], name: str) -> list[str]:
    aliases_raw = item.get("aliases") or []
    aliases: list[str] = []
    if isinstance(aliases_raw, list):
        for a in aliases_raw:
            t = _text(a)
            if t and t != name and t not in aliases:
                aliases.append(t)
    return aliases


def _entity_name(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        t = _text(item.get(key))
        if t:
            return t
    return ""


def _evidence_facts(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            fact = item.strip()
            if fact:
                out.append({"fact": fact, "evidence": "", "confidence": None})
            continue
        if not isinstance(item, dict):
            continue
        fact = _text(item.get("fact") or item.get("text") or item.get("description"))
        if not fact:
            continue
        out.append(
            {
                "fact": fact,
                "evidence": _text(item.get("evidence")),
                "confidence": _float_or_none(item.get("confidence")),
            }
        )
    return out


def _named_entity(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        name = item.strip()
        return {
            "name": name,
            "aliases": [],
            "evidence": "",
            "identity_hint": "",
        } if name else None
    if not isinstance(item, dict):
        return None
    name = _entity_name(
        item,
        "name",
        "item",
        "title",
        "object",
        "cue",
        "character",
        "location",
        "faction",
        "prop",
    )
    if not name:
        return None
    return {
        "name": name,
        "aliases": _aliases(item, name),
        "evidence": _text(item.get("evidence")),
        "identity_hint": _text(item.get("identity_hint")),
    }


def _character_mention(item: Any) -> dict[str, Any] | None:
    base = _named_entity(item)
    if not base:
        return None
    if isinstance(item, str):
        return {
            **base,
            "appearance": [],
            "personality": [],
            "actions": [],
            "emotion": "",
        }
    actions_raw = item.get("actions") or []
    actions: list[str] = []
    if isinstance(actions_raw, list):
        for a in actions_raw:
            t = _text(a)
            if t and t not in actions:
                actions.append(t)
    return {
        **base,
        "appearance": _evidence_facts(item.get("appearance")),
        "personality": _evidence_facts(item.get("personality")),
        "actions": actions,
        "emotion": _text(item.get("emotion")),
    }


def _location_mention(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        name = item.strip()
        return {
            "name": name,
            "aliases": [],
            "description": "",
            "atmosphere": "",
            "evidence": "",
        } if name else None
    if not isinstance(item, dict):
        return None
    name = _entity_name(item, "name", "title", "location", "place")
    if not name:
        return None
    return {
        "name": name,
        "aliases": _aliases(item, name),
        "description": _text(item.get("description")),
        "atmosphere": _text(item.get("atmosphere")),
        "evidence": _text(item.get("evidence")),
    }


def _string_cue(item: Any) -> str | None:
    if isinstance(item, str):
        t = item.strip()
        return t or None
    if not isinstance(item, dict):
        return None
    t = _text(
        item.get("description")
        or item.get("cue")
        or item.get("text")
        or item.get("dialogue")
        or item.get("note")
        or item.get("object")
        or item.get("summary")
        or item.get("scene")
    )
    return t or None


def _event(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        summary = item.strip()
        if not summary:
            return None
        return {
            "summary": summary,
            "evidence": "",
            "participants": [],
            "location": "",
            "time_hint": "",
            "cause": "",
            "process": "",
            "result": "",
            "importance": None,
            "visual_score": None,
        }
    if not isinstance(item, dict):
        return None
    summary = _text(
        item.get("summary")
        or item.get("description")
        or item.get("text")
        or item.get("event")
        or item.get("title")
    )
    if not summary:
        return None
    participants_raw = item.get("participants")
    participants: list[str] = []
    if isinstance(participants_raw, list):
        participants = [_text(x) for x in participants_raw if _text(x)]
    return {
        "summary": summary,
        "evidence": _text(item.get("evidence")),
        "participants": participants,
        "location": _text(item.get("location")),
        "time_hint": _text(item.get("time_hint") or item.get("story_time_hint")),
        "cause": _text(item.get("cause")),
        "process": _text(item.get("process")),
        "result": _text(item.get("result")),
        "importance": _float_or_none(item.get("importance")),
        "visual_score": _float_or_none(item.get("visual_score")),
    }


def _foreshadow(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        note = item.strip()
        return {"note": note, "evidence": ""} if note else None
    if not isinstance(item, dict):
        return None
    note = _text(
        item.get("note")
        or item.get("description")
        or item.get("text")
        or item.get("cue")
        or item.get("summary")
    )
    if not note:
        return None
    return {"note": note, "evidence": _text(item.get("evidence"))}


def _named_list(items: Any, factory) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        ent = factory(item)
        if not ent:
            continue
        key = ent["name"]
        if key in seen:
            continue
        seen.add(key)
        out.append(ent)
    return out


def _string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cue = _string_cue(item)
        if not cue or cue in seen:
            continue
        seen.add(cue)
        out.append(cue)
    return out


def _visual_candidates(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            scene = item.strip()
            if scene:
                out.append(
                    {
                        "scene": scene,
                        "evidence": "",
                        "visual_score": None,
                        "reason": "",
                        "suggested_shots": [],
                        "difficulty": "",
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        scene = _text(item.get("scene") or item.get("description") or item.get("text"))
        if not scene:
            continue
        shots = item.get("suggested_shots")
        suggested = [_text(s) for s in shots if _text(s)] if isinstance(shots, list) else []
        out.append(
            {
                "scene": scene,
                "evidence": _text(item.get("evidence")),
                "reason": _text(item.get("reason")),
                "visual_score": _float_or_none(item.get("visual_score")),
                "suggested_shots": suggested,
                "difficulty": _text(item.get("difficulty")),
            }
        )
    return out


def _count_missing_evidence(data: dict[str, Any]) -> int:
    missing = 0
    for key in ("characters", "locations", "factions", "props"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and not _text(item.get("evidence")):
                missing += 1
    for key in ("events", "foreshadowing", "visual_candidates"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and not _text(item.get("evidence")):
                missing += 1
    return missing


def coerce_extract(raw: Any) -> dict[str, Any]:
    """Normalize messy LLM JSON into ChunkExtract-compatible dict."""
    empty = {
        "summary": "",
        "characters": [],
        "locations": [],
        "factions": [],
        "props": [],
        "events": [],
        "foreshadowing": [],
        "relationships": [],
        "visual_cues": [],
        "visual_candidates": [],
        "voice_cues": [],
        "adaptation_notes": [],
        "quality": {
            "json_repaired": False,
            "missing_evidence_count": 0,
            "low_confidence_count": 0,
            "warnings": [],
        },
    }
    if not isinstance(raw, dict):
        return empty

    events: list[dict[str, Any]] = []
    for item in raw.get("events") or []:
        ev = _event(item)
        if ev:
            events.append(ev)

    foreshadowing: list[dict[str, Any]] = []
    for item in raw.get("foreshadowing") or []:
        fs = _foreshadow(item)
        if fs:
            foreshadowing.append(fs)

    relationships: list[dict[str, Any]] = []
    for item in raw.get("relationships") or []:
        if isinstance(item, dict):
            relationships.append(item)
        elif isinstance(item, str) and item.strip():
            relationships.append({"note": item.strip()})

    visual_candidates = _visual_candidates(raw.get("visual_candidates") or [])
    # Map legacy visual_cues into low-structure candidates when none provided.
    if not visual_candidates:
        for cue in _string_list(raw.get("visual_cues")):
            visual_candidates.append(
                {
                    "scene": cue,
                    "evidence": "",
                    "visual_score": None,
                    "reason": "from_visual_cues",
                    "suggested_shots": [],
                    "difficulty": "",
                }
            )

    data = {
        "summary": _text(raw.get("summary")),
        "characters": _named_list(raw.get("characters"), _character_mention),
        "locations": _named_list(raw.get("locations"), _location_mention),
        "factions": _named_list(raw.get("factions"), _named_entity),
        "props": _named_list(raw.get("props"), _named_entity),
        "events": events,
        "foreshadowing": foreshadowing,
        "relationships": relationships,
        "visual_cues": _string_list(raw.get("visual_cues")),
        "visual_candidates": visual_candidates,
        "voice_cues": _string_list(raw.get("voice_cues")),
        "adaptation_notes": _string_list(raw.get("adaptation_notes")),
    }
    missing = _count_missing_evidence(data)
    warnings: list[str] = []
    if missing:
        warnings.append(f"missing_evidence:{missing}")
    data["quality"] = {
        "json_repaired": bool(raw.get("_json_repaired")),
        "missing_evidence_count": missing,
        "low_confidence_count": 0,
        "warnings": warnings,
    }
    return data
