import json
from datetime import datetime, timezone
from pathlib import Path
from aivp.schemas import REQUIRED_BIBLE_KEYS


def assemble_bible(
    *,
    project_name: str,
    chapters: list[dict],
    entities: dict,
    events: list[dict],
    arcs: list[dict],
    extracts: list[dict],
    warnings: list[str] | None = None,
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

    chars = entities.get("characters", [])
    bible = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_stats": {"chapter_count": len(chapters), "event_count": len(events)},
        "warnings": warnings or [],
        "project_meta": {"title": project_name, "language": "zh-CN", "genre": "国风"},
        "logline": arcs[0]["summary"] if arcs else "",
        "worldbuilding": {"summary": "", "rules": []},
        "plot_structure": {"arcs": arcs, "chapters": [{"id": c["id"], "title": c["title"]} for c in chapters]},
        "characters": chars,
        "character_relations": [],
        "locations": entities.get("locations", []),
        "factions": entities.get("factions", []),
        "props": entities.get("props", []),
        "timeline": events,
        "foreshadowing": foreshadowing,
        "adaptation_notes": adaptation_notes,
        "visual_style": {"summary": "；".join(dict.fromkeys(visual_cues)), "keywords": list(dict.fromkeys(visual_cues))},
        "character_visuals": [{"character_id": c.get("id"), "name": c.get("name"), "notes": ""} for c in chars],
        "voice_bible": {"cues": list(dict.fromkeys(voice_cues)), "cast": []},
        "production_constraints": {"max_chars_on_screen": 3, "notes": []},
    }
    for k in REQUIRED_BIBLE_KEYS:
        bible.setdefault(k, {} if k not in ("characters", "character_relations", "locations", "factions", "props", "timeline", "foreshadowing", "adaptation_notes") else [])
    return bible


def run_assemble(paths, project_name: str, warnings: list[str] | None = None) -> dict:
    chapters = json.loads(paths.chapters_json.read_text(encoding="utf-8"))
    entities = json.loads(paths.entities_json.read_text(encoding="utf-8"))
    events = json.loads(paths.events_json.read_text(encoding="utf-8"))
    arcs = json.loads(paths.arcs_json.read_text(encoding="utf-8"))
    extracts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths.extract_dir.glob("*/*.json"))]
    bible = assemble_bible(
        project_name=project_name,
        chapters=chapters,
        entities=entities,
        events=events,
        arcs=arcs,
        extracts=extracts,
        warnings=warnings,
    )
    paths.auto_bible_json.parent.mkdir(parents=True, exist_ok=True)
    paths.auto_bible_json.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    return bible
