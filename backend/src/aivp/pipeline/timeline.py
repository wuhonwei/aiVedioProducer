import json
from pathlib import Path


def build_timeline(chunks_meta: list[dict], extracts: dict[tuple[str, str], dict]) -> list[dict]:
    ordered = sorted(chunks_meta, key=lambda c: (c["chapter_id"], c["index"]))
    events: list[dict] = []
    n = 1
    for c in ordered:
        key = (c["chapter_id"], c["id"])
        for ev in extracts.get(key, {}).get("events", []):
            events.append({
                "id": f"evt{n:04d}",
                "chapter_id": c["chapter_id"],
                "chunk_id": c["id"],
                "summary": ev.get("summary", ""),
                "raw": ev,
            })
            n += 1
    return events


def run_timeline(chunks_jsonl: Path, extract_dir: Path, out_json: Path) -> list[dict]:
    chunks_meta = [json.loads(l) for l in chunks_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    extracts: dict[tuple[str, str], dict] = {}
    for path in extract_dir.glob("*/*.json"):
        extracts[(path.parent.name, path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    events = build_timeline(chunks_meta, extracts)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    return events
