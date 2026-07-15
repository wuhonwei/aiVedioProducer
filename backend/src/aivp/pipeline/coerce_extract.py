from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_text(v) for v in value]
        return " ".join(p for p in parts if p).strip()
    return str(value).strip()


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
    name = _text(
        item.get("name")
        or item.get("item")
        or item.get("title")
        or item.get("object")
        or item.get("cue")
        or item.get("character")
        or item.get("location")
        or item.get("faction")
        or item.get("prop")
    )
    if not name:
        return None
    aliases_raw = item.get("aliases") or []
    aliases: list[str] = []
    if isinstance(aliases_raw, list):
        for a in aliases_raw:
            t = _text(a)
            if t and t != name and t not in aliases:
                aliases.append(t)
    return {
        "name": name,
        "aliases": aliases,
        "evidence": _text(item.get("evidence")),
        "identity_hint": _text(item.get("identity_hint")),
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
        return {"summary": summary, "evidence": ""} if summary else None
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
    out: dict[str, Any] = {
        "summary": summary,
        "evidence": _text(item.get("evidence")),
    }
    for key in ("type", "location", "time_hint", "cause", "process", "result"):
        if item.get(key):
            out[key] = _text(item.get(key))
    for key in ("participants",):
        raw = item.get(key)
        if isinstance(raw, list):
            out[key] = [_text(x) for x in raw if _text(x)]
    for key in ("importance", "visual_score"):
        if key in item:
            try:
                out[key] = float(item[key])
            except (TypeError, ValueError):
                pass
    return out


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


def _named_list(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        ent = _named_entity(item)
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
                out.append({"scene": scene, "evidence": "", "visual_score": 0.0})
            continue
        if not isinstance(item, dict):
            continue
        scene = _text(item.get("scene") or item.get("description") or item.get("text"))
        if not scene:
            continue
        entry: dict[str, Any] = {
            "scene": scene,
            "evidence": _text(item.get("evidence")),
            "reason": _text(item.get("reason")),
        }
        try:
            entry["visual_score"] = float(item.get("visual_score") or 0)
        except (TypeError, ValueError):
            entry["visual_score"] = 0.0
        shots = item.get("suggested_shots")
        if isinstance(shots, list):
            entry["suggested_shots"] = [_text(s) for s in shots if _text(s)]
        out.append(entry)
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

    data = {
        "summary": _text(raw.get("summary")),
        "characters": _named_list(raw.get("characters")),
        "locations": _named_list(raw.get("locations")),
        "factions": _named_list(raw.get("factions")),
        "props": _named_list(raw.get("props")),
        "events": events,
        "foreshadowing": foreshadowing,
        "relationships": relationships,
        "visual_cues": _string_list(raw.get("visual_cues")),
        "visual_candidates": _visual_candidates(raw.get("visual_candidates") or []),
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
