from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from aivp.jobs.control import JobCancelled
from aivp.pipeline.coerce_assets import (
    ensure_character_card,
    ensure_event_beat,
    ensure_faction_card,
    ensure_location_card,
    ensure_prop_card,
    index_llm_items,
)
from aivp.pipeline.select_majors import ENTITY_KEYS, select_majors
from aivp.pipeline.timeline import build_timeline

ASSET_SYSTEM = (
    "You enrich guofeng story bible assets for video. Output strict JSON with key items "
    "(array of objects). Each object needs name and production fields. "
    "Prefer evidence; mark guesses in inferred_fields. No markdown."
)

EVENT_SYSTEM = (
    "You enrich story events for storyboard hints. Output strict JSON with key events "
    "(array). Each event needs summary, cast[], visual_beat, camera_hint, emotion, "
    "dramatic_beat, duration_hint_sec. No markdown."
)


def _load_extracts(extract_dir) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(extract_dir.glob("*/*.json"))
    ]


def _chunks_meta(chunks_jsonl) -> list[dict]:
    return [
        json.loads(line)
        for line in chunks_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _extract_map(extract_dir) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in extract_dir.glob("*/*.json"):
        out[(path.parent.name, path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def _ensure_kind(kind: str, entity: dict, raw: dict | None, tier: str) -> dict:
    if kind == "characters":
        return ensure_character_card(entity, raw, tier=tier)
    if kind == "locations":
        return ensure_location_card(entity, raw, tier=tier)
    if kind == "props":
        return ensure_prop_card(entity, raw, tier=tier)
    return ensure_faction_card(entity, raw, tier=tier)


def _llm_batch(
    llm,
    *,
    kind: str,
    entities: list[dict],
    context: dict,
    should_cancel: Callable[[], bool] | None,
) -> dict[str, dict]:
    if not entities:
        return {}
    user = (
        f"kind={kind}\n"
        "Fill production-ready fields for these entities.\n"
        + json.dumps({"entities": entities, "context": context}, ensure_ascii=False)[
            :12000
        ]
    )
    try:
        raw = llm.complete_json(ASSET_SYSTEM, user, should_cancel=should_cancel)
    except JobCancelled:
        raise
    except Exception:
        return {}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        # Accept direct list or kind-named list (or extract-shaped leftovers).
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict) and isinstance(raw.get(kind), list):
            items = raw.get(kind)
        else:
            items = []
    return index_llm_items(items)


def build_assets(
    entities: dict,
    majors: dict[str, list[str]],
    llm,
    *,
    extracts: list[dict],
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, list[dict]]:
    context = {
        "sample_events": [
            (ex.get("events") or [None])[0]
            for ex in extracts[:12]
            if ex.get("events")
        ][:12]
    }
    assets: dict[str, list[dict]] = {k: [] for k in ENTITY_KEYS}
    major_sets = {k: set(v) for k, v in (majors or {}).items()}
    batches: list[tuple[str, list[dict]]] = []
    for kind in ENTITY_KEYS:
        major_ents = [
            e for e in entities.get(kind) or [] if e.get("id") in major_sets.get(kind, set())
        ]
        if major_ents:
            batches.append((kind, major_ents))

    total = max(len(batches), 1)
    done = 0
    if on_progress:
        on_progress(done, total)

    for kind, ents in batches:
        if should_cancel and should_cancel():
            raise JobCancelled("enrich_assets")
        llm_map: dict[str, dict] = {}
        if llm is not None:
            llm_map = _llm_batch(
                llm,
                kind=kind,
                entities=ents,
                context=context,
                should_cancel=should_cancel,
            )
        for ent in ents:
            raw = llm_map.get(str(ent.get("id"))) or llm_map.get(str(ent.get("name")))
            assets[kind].append(_ensure_kind(kind, ent, raw, "major"))
        done += 1
        if on_progress:
            on_progress(done, total)

    for kind in ENTITY_KEYS:
        major_ids = major_sets.get(kind, set())
        for ent in entities.get(kind) or []:
            if ent.get("id") in major_ids:
                continue
            assets[kind].append(_ensure_kind(kind, ent, None, "minor"))
    return assets


def enrich_event_list(
    events: list[dict],
    character_names: list[str],
    llm,
    *,
    should_cancel: Callable[[], bool] | None = None,
    window: int = 40,
) -> list[dict]:
    if not events:
        return []
    window = max(1, int(window or 40))
    llm_map: dict[str, dict] = {}
    if llm is not None:
        for start in range(0, len(events), window):
            if should_cancel and should_cancel():
                raise JobCancelled("enrich_events")
            batch = events[start : start + window]
            payload = {"events": batch, "characters": character_names[:40]}
            try:
                raw = llm.complete_json(
                    EVENT_SYSTEM,
                    "Enrich these events for video beats:\n"
                    + json.dumps(payload, ensure_ascii=False)[:12000],
                    should_cancel=should_cancel,
                )
                items = raw.get("events") if isinstance(raw, dict) else None
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            key = str(item.get("id") or item.get("summary") or "")
                            if key:
                                llm_map[key] = item
            except JobCancelled:
                raise
            except Exception:
                continue

    out: list[dict] = []
    for ev in events:
        raw = llm_map.get(str(ev.get("id"))) or llm_map.get(str(ev.get("summary")))
        out.append(ensure_event_beat(ev, raw, character_names))
    return out


def run_enrich(
    paths,
    settings,
    llm,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    if (
        not force
        and paths.assets_json.exists()
        and paths.majors_json.exists()
        and paths.events_enriched_json.exists()
    ):
        return {
            "majors": json.loads(paths.majors_json.read_text(encoding="utf-8")),
            "assets": json.loads(paths.assets_json.read_text(encoding="utf-8")),
            "events": json.loads(paths.events_enriched_json.read_text(encoding="utf-8")),
            "warnings": ["enrich_skipped_existing"],
            "skipped": True,
        }

    entities = json.loads(paths.entities_json.read_text(encoding="utf-8"))
    extracts = _load_extracts(paths.extract_dir)
    chunks = _chunks_meta(paths.chunks_jsonl)
    extract_map = _extract_map(paths.extract_dir)
    draft_events = build_timeline(chunks, extract_map)

    limits = {
        "characters": settings.enrich_top_characters,
        "locations": settings.enrich_top_locations,
        "props": settings.enrich_top_props,
        "factions": settings.enrich_top_factions,
    }
    selection = select_majors(
        entities,
        extracts,
        event_summaries=[str(e.get("summary") or "") for e in draft_events],
        limits=limits,
    )

    try:
        assets = build_assets(
            entities,
            selection["majors"],
            llm,
            extracts=extracts,
            should_cancel=should_cancel,
            on_progress=on_progress,
        )
    except JobCancelled:
        raise
    except Exception as e:  # noqa: BLE001
        warnings.append(f"enrich_assets_failed:{e}")
        if settings.enrich_strict:
            raise
        assets = {k: [] for k in ENTITY_KEYS}
        for kind in ENTITY_KEYS:
            for ent in entities.get(kind) or []:
                tier = (
                    "major"
                    if ent.get("id") in set(selection["majors"].get(kind) or [])
                    else "minor"
                )
                assets[kind].append(_ensure_kind(kind, ent, None, tier))

    char_names = [str(c.get("name")) for c in assets.get("characters") or [] if c.get("name")]
    try:
        events = enrich_event_list(
            draft_events,
            char_names,
            llm,
            should_cancel=should_cancel,
            window=getattr(settings, "enrich_event_window", 40),
        )
    except JobCancelled:
        raise
    except Exception as e:  # noqa: BLE001
        warnings.append(f"enrich_events_failed:{e}")
        if settings.enrich_strict:
            raise
        events = [
            ensure_event_beat(ev, None, char_names) for ev in draft_events
        ]

    # If no factions extracted, leave empty (do not invent org without name seed).
    paths.enrich_dir.mkdir(parents=True, exist_ok=True)
    paths.majors_json.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.assets_json.write_text(
        json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.events_enriched_json.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "majors": selection,
        "assets": assets,
        "events": events,
        "warnings": warnings,
        "skipped": False,
    }
