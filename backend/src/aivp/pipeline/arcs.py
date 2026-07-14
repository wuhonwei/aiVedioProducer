import json
from pathlib import Path


def build_arcs(chapters: list[dict], events: list[dict]) -> list[dict]:
    by_ch: dict[str, list[str]] = {}
    for e in events:
        by_ch.setdefault(e["chapter_id"], []).append(e["summary"])
    arcs = []
    for ch in chapters:
        summaries = by_ch.get(ch["id"], [])
        arcs.append({
            "id": f"arc_{ch['id']}",
            "chapter_id": ch["id"],
            "title": ch["title"],
            "summary": "；".join(summaries) if summaries else "",
        })
    return arcs


def run_arcs(chapters_json: Path, events_json: Path, out_json: Path) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    events = json.loads(events_json.read_text(encoding="utf-8"))
    arcs = build_arcs(chapters, events)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(arcs, ensure_ascii=False, indent=2), encoding="utf-8")
    return arcs
