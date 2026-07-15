from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.schemas import REQUIRED_BIBLE_KEYS

SYNTH_SYSTEM = (
    "\u4f60\u662f\u56fd\u98ce\u957f\u7bc7\u5c0f\u8bf4\u8d23\u4efb\u7f16\u8f91\u3002"
    "\u6839\u636e\u7ed9\u5b9a\u7684\u5b9e\u4f53\u3001\u7ae0\u8282\u4e0e\u4e8b\u4ef6\u6458\u8981\uff0c\u8f93\u51fa\u4e25\u683c JSON\uff0c"
    "\u952e\u5fc5\u987b\u5305\u542b: logline(string), worldbuilding({summary, rules[]}), "
    "character_relations([{source, target, relation}]), plot_overview(string)\u3002"
    "\u7f3a\u4fe1\u606f\u7528\u7a7a\u5b57\u7b26\u4e32\u6216\u7a7a\u6570\u7ec4\u3002\u4e0d\u8981\u8f93\u51fa markdown\u3002"
)


def _names(items: list[dict], key: str = "name") -> list[str]:
    out: list[str] = []
    for item in items:
        name = str(item.get(key, "")).strip()
        if name:
            out.append(name)
    return out


def _heuristic_logline(
    project_name: str, arcs: list[dict], events: list[dict], characters: list[dict]
) -> str:
    for arc in arcs:
        summary = str(arc.get("summary", "")).strip()
        if summary:
            return summary[:120]
    summaries = [
        str(e.get("summary", "")).strip()
        for e in events
        if str(e.get("summary", "")).strip()
    ]
    if summaries:
        return ("\uFF1B".join(summaries[:5]))[:120]
    leads = _names(characters)[:3]
    if leads:
        return "\u300a%s\u300b\u56f4\u7ed5%s\u5c55\u5f00\u7684\u6545\u4e8b\u3002" % (
            project_name,
            "\u3001".join(leads),
        )
    return "\u300a%s\u300b\u6545\u4e8b\u6982\u8981\u5f85\u8865\u5168\u3002" % project_name


def _heuristic_worldbuilding(entities: dict, extracts: list[dict]) -> dict[str, Any]:
    locations = _names(entities.get("locations", []))
    factions = _names(entities.get("factions", []))
    props = _names(entities.get("props", []))
    cues: list[str] = []
    for ex in extracts:
        for c in ex.get("visual_cues", []) or []:
            text = str(c).strip()
            if text:
                cues.append(text)
    parts: list[str] = []
    if locations:
        parts.append("\u4e3b\u8981\u5730\u70b9\uff1a%s\u3002" % "\u3001".join(locations[:12]))
    if factions:
        parts.append("\u52bf\u529b/\u7ec4\u7ec7\uff1a%s\u3002" % "\u3001".join(factions[:12]))
    if props:
        parts.append("\u5173\u952e\u7269\u4ef6\uff1a%s\u3002" % "\u3001".join(props[:12]))
    if cues:
        parts.append(
            "\u6c1b\u56f4\u610f\u8c61\uff1a%s\u3002"
            % "\u3001".join(list(dict.fromkeys(cues))[:12])
        )
    rules: list[str] = []
    if factions:
        rules.append(
            "\u591a\u65b9\u52bf\u529b\u5e76\u884c\uff0c\u7acb\u573a\u51b2\u7a81\u63a8\u52a8\u53d9\u4e8b\u3002"
        )
    if props:
        rules.append(
            "\u5173\u952e\u9053\u5177\u53ef\u80fd\u7ed1\u5b9a\u4fee\u70bc\u3001\u7981\u5fcc\u6216\u547d\u8fd0\u7ebf\u7d22\u3002"
        )
    return {
        "summary": "".join(parts)
        if parts
        else "\u4e16\u754c\u89c2\u7ec6\u8282\u5f85\u4ece\u539f\u6587\u8fdb\u4e00\u6b65\u5f52\u7eb3\u3002",
        "rules": rules,
        "locations": locations[:24],
        "factions": factions[:24],
        "props": props[:24],
    }


def _heuristic_relations(characters: list[dict], events: list[dict]) -> list[dict[str, str]]:
    names = _names(characters)
    if len(names) < 2:
        return []
    relations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        summary = str(event.get("summary", ""))
        present = [n for n in names if n in summary]
        if len(present) < 2:
            continue
        a, b = present[0], present[1]
        key = (a, b) if a <= b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source": a,
                "target": b,
                "relation": "\u540c\u884c/\u5e76\u73b0\u4e8e\u540c\u4e00\u4e8b\u4ef6",
            }
        )
        if len(relations) >= 12:
            break
    return relations


def synthesize_overview(
    llm,
    *,
    project_name: str,
    chapters: list[dict],
    entities: dict,
    events: list[dict],
    arcs: list[dict],
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    payload = {
        "title": project_name,
        "chapters": [{"id": c.get("id"), "title": c.get("title")} for c in chapters[:80]],
        "characters": entities.get("characters", [])[:40],
        "locations": entities.get("locations", [])[:40],
        "factions": entities.get("factions", [])[:40],
        "props": entities.get("props", [])[:40],
        "arcs": arcs[:40],
        "events": [
            {
                "summary": e.get("summary"),
                "chapter_id": e.get("chapter_id"),
                "visual_beat": e.get("visual_beat"),
            }
            for e in events[:80]
        ],
    }
    user = (
        "\u8bf7\u6839\u636e\u4e0b\u5217\u7ed3\u6784\u5316\u7d20\u6750\uff0c"
        "\u4e3a\u56fd\u98ce\u957f\u7bc7\u5199\u51fa\u6545\u4e8b\u4e00\u53e5\u8bdd\u6982\u62ec\u4e0e\u4e16\u754c\u89c2\u8bbe\u5b9a\uff1a\n"
        + json.dumps(payload, ensure_ascii=False)[:14000]
    )
    return llm.complete_json(SYNTH_SYSTEM, user, should_cancel=should_cancel)


def _entities_from_assets(assets: dict | None, fallback: dict) -> dict:
    if not assets:
        return fallback
    out = {}
    for key in ("characters", "locations", "factions", "props"):
        items = assets.get(key) if isinstance(assets.get(key), list) else None
        out[key] = items if items else fallback.get(key, [])
    return out


def assemble_bible(
    *,
    project_name: str,
    chapters: list[dict],
    entities: dict,
    events: list[dict],
    arcs: list[dict],
    extracts: list[dict],
    warnings: list[str] | None = None,
    llm=None,
    should_cancel: Callable[[], bool] | None = None,
    assets: dict | None = None,
) -> dict:
    foreshadowing: list = []
    visual_cues: list[str] = []
    voice_cues: list[str] = []
    adaptation_notes: list[str] = []
    for ex in extracts:
        foreshadowing.extend(ex.get("foreshadowing", []))
        visual_cues.extend(ex.get("visual_cues", []))
        voice_cues.extend(ex.get("voice_cues", []))
        adaptation_notes.extend(ex.get("adaptation_notes", []))

    merged = _entities_from_assets(assets, entities)
    chars = merged.get("characters", [])
    warn = list(warnings or [])
    logline = _heuristic_logline(project_name, arcs, events, chars)
    worldbuilding = _heuristic_worldbuilding(merged, extracts)
    relations = _heuristic_relations(chars, events)

    if llm is not None:
        try:
            synth = synthesize_overview(
                llm,
                project_name=project_name,
                chapters=chapters,
                entities=merged,
                events=events,
                arcs=arcs,
                should_cancel=should_cancel,
            )
            if isinstance(synth.get("logline"), str) and synth["logline"].strip():
                logline = synth["logline"].strip()
            wb = synth.get("worldbuilding")
            if isinstance(wb, dict) and (wb.get("summary") or wb.get("rules")):
                worldbuilding = {
                    "summary": str(
                        wb.get("summary") or worldbuilding.get("summary") or ""
                    ),
                    "rules": (
                        wb.get("rules")
                        if isinstance(wb.get("rules"), list)
                        else worldbuilding.get("rules", [])
                    ),
                    "locations": worldbuilding.get("locations", []),
                    "factions": worldbuilding.get("factions", []),
                    "props": worldbuilding.get("props", []),
                }
            cr = synth.get("character_relations")
            if isinstance(cr, list) and cr:
                relations = cr
        except Exception as e:  # noqa: BLE001
            warn.append(f"synth_overview_failed:{e}")

    visual_keywords = [str(v).strip() for v in visual_cues if str(v).strip()]
    for loc in merged.get("locations") or []:
        for color in loc.get("palette") or []:
            if color:
                visual_keywords.append(str(color))
        if loc.get("era_mood"):
            visual_keywords.append(str(loc["era_mood"]))
    for ch in chars:
        for color in (ch.get("wardrobe") or {}).get("colors") or []:
            if color:
                visual_keywords.append(str(color))
        if (ch.get("wardrobe") or {}).get("default"):
            visual_keywords.append(str(ch["wardrobe"]["default"]))
    visual_keywords = list(dict.fromkeys(visual_keywords))

    voice_list = [str(v).strip() for v in voice_cues if str(v).strip()]
    voice_list = list(dict.fromkeys(voice_list))
    adapt_list = [str(v).strip() for v in adaptation_notes if str(v).strip()]
    adapt_list = list(dict.fromkeys(adapt_list))
    if isinstance(foreshadowing, list):
        foreshadowing = [
            {"note": str(x)} if isinstance(x, str) else x for x in foreshadowing
        ]

    character_visuals = []
    cast = []
    anchors: list[str] = []
    for c in chars:
        name = str(c.get("name") or "")
        appearance = c.get("appearance") if isinstance(c.get("appearance"), dict) else {}
        wardrobe = c.get("wardrobe") if isinstance(c.get("wardrobe"), dict) else {}
        notes_parts = [
            str(appearance.get("face") or ""),
            str(appearance.get("hair") or ""),
            str(wardrobe.get("default") or ""),
            str(c.get("prompt_zh") or ""),
        ]
        notes = "\uFF1B".join([p for p in notes_parts if p])
        if not notes:
            related = [v for v in visual_keywords if name and name in v][:5]
            notes = "\uFF1B".join(related)
        character_visuals.append(
            {
                "character_id": c.get("id"),
                "name": name,
                "notes": notes,
                "prompt_zh": c.get("prompt_zh") or "",
                "consistency_anchors": c.get("consistency_anchors") or [],
            }
        )
        voice = c.get("voice") if isinstance(c.get("voice"), dict) else {}
        cue = "\uFF1B".join(
            [
                str(voice.get("timbre") or ""),
                str(voice.get("pace") or ""),
                *list(voice.get("speech_habits") or [])[:2],
            ]
        ).strip("\uFF1B")
        cast.append({"name": name, "cue": cue, "voice": voice})
        for a in c.get("consistency_anchors") or []:
            if a and a not in anchors:
                anchors.append(str(a))

    style_anchors = []
    for loc in merged.get("locations") or []:
        if loc.get("tier") == "major" and loc.get("prompt_zh"):
            style_anchors.append(str(loc["prompt_zh"])[:80])
    style_anchors = list(dict.fromkeys(style_anchors + visual_keywords))[:24]

    max_cast = 1
    for ev in events:
        cast_n = len(ev.get("cast") or [])
        if cast_n > max_cast:
            max_cast = cast_n
    max_chars = min(max(max_cast, 2), 5)

    bible = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_stats": {
            "chapter_count": len(chapters),
            "event_count": len(events),
            "video_ready": True,
        },
        "warnings": warn,
        "project_meta": {
            "title": project_name,
            "language": "zh-CN",
            "genre": "\u56fd\u98ce",
        },
        "logline": logline,
        "worldbuilding": worldbuilding,
        "plot_structure": {
            "arcs": arcs,
            "chapters": [{"id": c["id"], "title": c["title"]} for c in chapters],
        },
        "characters": chars,
        "character_relations": relations,
        "locations": merged.get("locations", []),
        "factions": merged.get("factions", []),
        "props": merged.get("props", []),
        "timeline": events,
        "foreshadowing": foreshadowing,
        "adaptation_notes": adapt_list,
        "visual_style": {
            "summary": "\uFF1B".join(style_anchors[:12]),
            "keywords": visual_keywords,
            "style_anchors": style_anchors,
        },
        "character_visuals": character_visuals,
        "voice_bible": {"cues": voice_list, "cast": cast},
        "production_constraints": {
            "max_chars_on_screen": max_chars,
            "notes": adapt_list[:8],
            "consistency_anchors": anchors[:24],
            "forbidden": ["\u73b0\u4ee3\u5143\u7d20", "\u975e\u56fd\u98ce\u670d\u9970\u4e32\u620f"],
        },
    }
    for k in REQUIRED_BIBLE_KEYS:
        bible.setdefault(
            k,
            {}
            if k
            not in (
                "characters",
                "character_relations",
                "locations",
                "factions",
                "props",
                "timeline",
                "foreshadowing",
                "adaptation_notes",
            )
            else [],
        )
    return bible


def run_assemble(
    paths,
    project_name: str,
    warnings: list[str] | None = None,
    llm=None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    chapters = json.loads(paths.chapters_json.read_text(encoding="utf-8"))
    entities = json.loads(paths.entities_json.read_text(encoding="utf-8"))
    events = json.loads(paths.events_json.read_text(encoding="utf-8"))
    arcs = json.loads(paths.arcs_json.read_text(encoding="utf-8"))
    extracts = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(paths.extract_dir.glob("*/*.json"))
    ]
    assets = None
    if paths.assets_json.exists():
        assets = json.loads(paths.assets_json.read_text(encoding="utf-8"))
    bible = assemble_bible(
        project_name=project_name,
        chapters=chapters,
        entities=entities,
        events=events,
        arcs=arcs,
        extracts=extracts,
        warnings=warnings,
        llm=llm,
        should_cancel=should_cancel,
        assets=assets,
    )
    paths.auto_bible_json.parent.mkdir(parents=True, exist_ok=True)
    paths.auto_bible_json.write_text(
        json.dumps(bible, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    from aivp.bible.meta import persist_merged_bible

    persist_merged_bible(
        auto_path=paths.auto_bible_json,
        overlay_path=paths.overlay_json,
        merged_path=paths.merged_bible_json,
        meta_path=paths.bible_meta_json,
    )
    return bible
