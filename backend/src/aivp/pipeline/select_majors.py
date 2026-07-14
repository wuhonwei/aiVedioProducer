from __future__ import annotations

from collections import Counter
from typing import Any


ENTITY_KEYS = ("characters", "locations", "factions", "props")


def _count_mentions(name: str, aliases: list[str], texts: list[str]) -> int:
    keys = [name, *[a for a in aliases if a]]
    total = 0
    for text in texts:
        if not text:
            continue
        for key in keys:
            if key and key in text:
                total += text.count(key)
    return total


def select_majors(
    entities: dict[str, list[dict]],
    extracts: list[dict],
    *,
    event_summaries: list[str] | None = None,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Rank entities and mark majors by frequency in extracts/events."""
    limits = {
        "characters": 8,
        "locations": 8,
        "factions": 4,
        "props": 6,
        **(limits or {}),
    }
    blob_parts: list[str] = []
    for ex in extracts:
        for key in ENTITY_KEYS:
            for item in ex.get(key) or []:
                if isinstance(item, dict):
                    blob_parts.append(str(item.get("name") or ""))
                    blob_parts.extend(str(a) for a in (item.get("aliases") or []))
                else:
                    blob_parts.append(str(item))
        for ev in ex.get("events") or []:
            if isinstance(ev, dict):
                blob_parts.append(
                    str(ev.get("summary") or ev.get("description") or "")
                )
            else:
                blob_parts.append(str(ev))
        for cue in ex.get("visual_cues") or []:
            blob_parts.append(str(cue) if not isinstance(cue, dict) else str(cue))
    blob_parts.extend(event_summaries or [])
    texts = [t for t in blob_parts if t]

    ranked: dict[str, list[dict]] = {}
    majors: dict[str, list[str]] = {}
    for kind in ENTITY_KEYS:
        scored: list[tuple[int, dict]] = []
        for ent in entities.get(kind) or []:
            name = str(ent.get("name") or "").strip()
            if not name:
                continue
            aliases = [str(a) for a in (ent.get("aliases") or [])]
            score = _count_mentions(name, aliases, texts)
            # Base presence score so every entity can still rank.
            score += 1
            scored.append((score, ent))
        scored.sort(key=lambda x: (-x[0], x[1].get("name") or ""))
        ranked[kind] = [
            {
                "id": e.get("id"),
                "name": e.get("name"),
                "score": s,
            }
            for s, e in scored
        ]
        top = scored[: max(0, int(limits.get(kind, 0)))]
        majors[kind] = [str(e.get("id")) for _, e in top if e.get("id")]

    return {"majors": majors, "ranked": ranked}
