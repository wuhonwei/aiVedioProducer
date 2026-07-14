from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.jobs.control import JobCancelled

SHOT_SYSTEM = (
    "You are a guofeng anime storyboard director. Output strict JSON object with key "
    '"shots" (array). Each shot must include: event_id, order, shot_type, camera, '
    "action, dialogue, duration_sec, visual_prompt, audio_notes, cast (string array), "
    "location_name. Expand each story event into 1-4 cinematic shots. "
    "visual_prompt must be production-ready Chinese and keep character consistency anchors. "
    "No markdown."
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_text(v) for v in value if _text(v))
    return str(value).strip()


def _asset_index(assets: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not assets:
        return out
    for kind in ("characters", "locations", "props", "factions"):
        for item in assets.get(kind) or []:
            name = _text(item.get("name"))
            if name:
                out[name] = item
            eid = _text(item.get("id"))
            if eid:
                out[eid] = item
    return out


def heuristic_shots_for_event(event: dict, assets_by_name: dict[str, dict]) -> list[dict]:
    event_id = _text(event.get("id")) or "evt"
    chapter_id = _text(event.get("chapter_id"))
    summary = _text(event.get("summary"))
    visual = _text(event.get("visual_beat")) or summary
    camera = _text(event.get("camera_hint")) or "中景稳拍"
    cast = event.get("cast") if isinstance(event.get("cast"), list) else []
    cast_names = [_text(c) for c in cast if _text(c)]
    location_name = ""
    for name in cast_names:
        # prefer named locations in summary
        pass
    for name, card in assets_by_name.items():
        if card.get("tier") == "major" and name and name in (summary + visual):
            if "era_mood" in card or "establishing_shot" in card:
                location_name = name
                break
    anchors = []
    for name in cast_names:
        card = assets_by_name.get(name) or {}
        if card.get("prompt_zh"):
            anchors.append(_text(card["prompt_zh"])[:120])
    if location_name and assets_by_name.get(location_name, {}).get("prompt_zh"):
        anchors.append(_text(assets_by_name[location_name]["prompt_zh"])[:120])
    prompt = "；".join([visual, *anchors[:3]])
    duration = int(event.get("duration_hint_sec") or 4)
    establishing = {
        "event_id": event_id,
        "chapter_id": chapter_id,
        "order": 1,
        "shot_type": "establishing" if location_name else "wide",
        "camera": camera,
        "action": visual or summary,
        "dialogue": "",
        "duration_sec": max(2, min(duration, 8)),
        "visual_prompt": prompt or summary,
        "audio_notes": _text(event.get("emotion")) or "环境声",
        "cast": cast_names,
        "location_name": location_name,
    }
    close = dict(establishing)
    close.update(
        {
            "order": 2,
            "shot_type": "medium" if cast_names else "insert",
            "camera": "中近景，跟随表情/物件",
            "action": summary,
            "duration_sec": max(2, min(duration // 2 or 3, 6)),
        }
    )
    return [establishing, close] if cast_names else [establishing]


def coerce_shot(raw: Any, event: dict, order_fallback: int) -> dict | None:
    if isinstance(raw, str):
        raw = {"action": raw, "visual_prompt": raw}
    if not isinstance(raw, dict):
        return None
    event_id = _text(raw.get("event_id") or event.get("id"))
    order = int(raw.get("order") or order_fallback)
    action = _text(raw.get("action") or raw.get("visual_prompt") or event.get("summary"))
    if not action:
        return None
    cast = raw.get("cast") if isinstance(raw.get("cast"), list) else event.get("cast") or []
    cast_names = [_text(c) for c in cast if _text(c)]
    return {
        "shot_id": _text(raw.get("shot_id")) or f"sh_{event_id}_{order:02d}",
        "event_id": event_id,
        "chapter_id": _text(raw.get("chapter_id") or event.get("chapter_id")),
        "order": order,
        "shot_type": _text(raw.get("shot_type")) or "medium",
        "camera": _text(raw.get("camera") or event.get("camera_hint")) or "中景",
        "action": action,
        "dialogue": _text(raw.get("dialogue")),
        "duration_sec": int(raw.get("duration_sec") or event.get("duration_hint_sec") or 3),
        "visual_prompt": _text(raw.get("visual_prompt")) or action,
        "audio_notes": _text(raw.get("audio_notes") or event.get("emotion")),
        "cast": cast_names,
        "location_name": _text(raw.get("location_name")),
    }


def build_event_payload(events: list[dict], assets: dict | None) -> list[dict]:
    idx = _asset_index(assets)
    payload = []
    for ev in events:
        cast = [_text(c) for c in (ev.get("cast") or []) if _text(c)]
        related = []
        for name in cast:
            card = idx.get(name)
            if card:
                related.append(
                    {
                        "name": name,
                        "prompt_zh": card.get("prompt_zh"),
                        "consistency_anchors": card.get("consistency_anchors") or [],
                    }
                )
        payload.append(
            {
                "id": ev.get("id"),
                "chapter_id": ev.get("chapter_id"),
                "summary": ev.get("summary"),
                "visual_beat": ev.get("visual_beat"),
                "camera_hint": ev.get("camera_hint"),
                "emotion": ev.get("emotion"),
                "dramatic_beat": ev.get("dramatic_beat"),
                "duration_hint_sec": ev.get("duration_hint_sec"),
                "cast": cast,
                "cast_assets": related,
            }
        )
    return payload


def expand_events_with_llm(
    events: list[dict],
    assets: dict | None,
    llm,
    *,
    batch_size: int = 8,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    shots: list[dict] = []
    idx = _asset_index(assets)
    if not events:
        return [], warnings

    batches = [events[i : i + batch_size] for i in range(0, len(events), batch_size)]
    total = len(batches)
    done = 0
    if on_progress:
        on_progress(0, total)

    for batch in batches:
        if should_cancel and should_cancel():
            raise JobCancelled("shot_script")
        payload = {"events": build_event_payload(batch, assets)}
        batch_shots: list[dict] = []
        try:
            if llm is None:
                raise RuntimeError("no_llm")
            raw = llm.complete_json(
                SHOT_SYSTEM,
                "Expand these story events into guofeng anime storyboard shots:\n"
                + json.dumps(payload, ensure_ascii=False)[:14000],
                should_cancel=should_cancel,
            )
            items = raw.get("shots") if isinstance(raw, dict) else None
            if not isinstance(items, list):
                raise ValueError("missing_shots_array")
            by_event: dict[str, list[dict]] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                eid = _text(item.get("event_id"))
                by_event.setdefault(eid, []).append(item)
            for ev in batch:
                eid = _text(ev.get("id"))
                raw_list = by_event.get(eid) or []
                if not raw_list:
                    batch_shots.extend(heuristic_shots_for_event(ev, idx))
                    continue
                for i, item in enumerate(raw_list, start=1):
                    shot = coerce_shot(item, ev, i)
                    if shot:
                        batch_shots.append(shot)
        except JobCancelled:
            raise
        except Exception as e:  # noqa: BLE001
            warnings.append(f"shot_batch_failed:{e}")
            for ev in batch:
                batch_shots.extend(heuristic_shots_for_event(ev, idx))

        shots.extend(batch_shots)
        done += 1
        if on_progress:
            on_progress(done, total)

    # Stable shot_id rewrite
    for i, shot in enumerate(shots, start=1):
        eid = shot.get("event_id") or "evt"
        order = int(shot.get("order") or 1)
        shot["shot_id"] = f"sh_{eid}_{order:02d}"
        shot["global_order"] = i
    return shots, warnings


def run_shot_script(
    paths,
    settings,
    llm,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not force and paths.shot_script_json.exists():
        existing = json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
        return {**existing, "skipped": True}

    if not paths.events_json.exists() and not paths.auto_bible_json.exists():
        raise FileNotFoundError("timeline_or_bible_missing")

    if paths.events_json.exists():
        events = json.loads(paths.events_json.read_text(encoding="utf-8"))
    else:
        bible = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
        events = bible.get("timeline") or []

    assets = None
    if paths.assets_json.exists():
        assets = json.loads(paths.assets_json.read_text(encoding="utf-8"))
    elif paths.auto_bible_json.exists():
        bible = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
        assets = {
            "characters": bible.get("characters") or [],
            "locations": bible.get("locations") or [],
            "props": bible.get("props") or [],
            "factions": bible.get("factions") or [],
        }

    shots, warnings = expand_events_with_llm(
        events,
        assets,
        llm,
        batch_size=settings.shot_batch_size,
        should_cancel=should_cancel,
        on_progress=on_progress,
    )
    if settings.shot_strict and any(w.startswith("shot_batch_failed") for w in warnings):
        raise RuntimeError(warnings[0])

    doc = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": getattr(llm, "model", "unknown"),
        "event_count": len(events),
        "shot_count": len(shots),
        "shots": shots,
        "warnings": warnings,
    }
    paths.shot_script_dir.mkdir(parents=True, exist_ok=True)
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return doc
