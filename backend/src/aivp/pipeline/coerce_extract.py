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
        return {"name": name, "aliases": []} if name else None
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
    return {"name": name, "aliases": aliases}


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
    )
    return t or None


def _event(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        summary = item.strip()
        return {"summary": summary} if summary else None
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
    out: dict[str, Any] = {"summary": summary}
    if item.get("type"):
        out["type"] = _text(item.get("type"))
    return out


def _foreshadow(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        note = item.strip()
        return {"note": note} if note else None
    if not isinstance(item, dict):
        return None
    note = _text(
        item.get("note")
        or item.get("description")
        or item.get("text")
        or item.get("cue")
        or item.get("summary")
    )
    return {"note": note} if note else None


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


def coerce_extract(raw: Any) -> dict[str, Any]:
    """Normalize messy LLM JSON into ChunkExtract-compatible dict."""
    if not isinstance(raw, dict):
        return {
            "characters": [],
            "locations": [],
            "factions": [],
            "props": [],
            "events": [],
            "foreshadowing": [],
            "visual_cues": [],
            "voice_cues": [],
            "adaptation_notes": [],
        }

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

    return {
        "characters": _named_list(raw.get("characters")),
        "locations": _named_list(raw.get("locations")),
        "factions": _named_list(raw.get("factions")),
        "props": _named_list(raw.get("props")),
        "events": events,
        "foreshadowing": foreshadowing,
        "visual_cues": _string_list(raw.get("visual_cues")),
        "voice_cues": _string_list(raw.get("voice_cues")),
        "adaptation_notes": _string_list(raw.get("adaptation_notes")),
    }
