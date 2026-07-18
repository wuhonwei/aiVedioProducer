"""Helpers to rebuild expression_dims onto bible character cards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aivp.bible.expression_dims import build_expression_dims, merge_expression_dims
from aivp.paths import ProjectPaths


def load_enrich_events(paths: ProjectPaths) -> list[dict[str, Any]]:
    for path in (paths.events_enriched_json, paths.events_json):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)]
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return [e for e in data["events"] if isinstance(e, dict)]
    return []


def rebuild_character_expression_dims(
    character: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    max_dims: int = 8,
) -> dict[str, Any]:
    """Return a copy of character with merged expression_dims."""
    ch = dict(character)
    incoming = build_expression_dims(ch, events, max_dims=max_dims)
    existing = ch.get("expression_dims") if isinstance(ch.get("expression_dims"), list) else []
    ch["expression_dims"] = merge_expression_dims(existing, incoming)
    return ch


def rebuild_all_major_expression_dims(
    bible: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    character_ids: list[str] | None = None,
    max_dims: int = 8,
) -> dict[str, Any]:
    """Update characters in a bible dict; returns new bible copy."""
    out = dict(bible)
    chars = list(out.get("characters") or [])
    want = set(character_ids) if character_ids else None
    updated: list[dict[str, Any]] = []
    for ch in chars:
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("id") or "")
        tier = str(ch.get("tier") or "major")
        if want is not None:
            if cid in want:
                updated.append(
                    rebuild_character_expression_dims(ch, events, max_dims=max_dims)
                )
            else:
                updated.append(ch)
            continue
        if tier == "major":
            updated.append(
                rebuild_character_expression_dims(ch, events, max_dims=max_dims)
            )
        else:
            updated.append(ch)
    out["characters"] = updated
    return out


def write_characters_overlay(paths: ProjectPaths, characters: list[dict[str, Any]]) -> None:
    """Snapshot characters list into overlay and leave other overlay keys intact."""
    overlay: dict[str, Any] = {}
    if paths.overlay_json.exists():
        try:
            overlay = json.loads(paths.overlay_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            overlay = {}
        if not isinstance(overlay, dict):
            overlay = {}
    overlay["characters"] = characters
    paths.overlay_json.parent.mkdir(parents=True, exist_ok=True)
    paths.overlay_json.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8"
    )
