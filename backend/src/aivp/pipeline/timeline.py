import json
import re
from pathlib import Path


def _norm_summary(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r'[，。！？、；：:“”"\'（）()【】\[\]…—\-]+', "", s)
    return s


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _event_fields(ev: dict) -> dict:
    participants = ev.get("participants") or []
    if not isinstance(participants, list):
        participants = [str(participants)] if participants else []
    return {
        "participants": [str(x).strip() for x in participants if str(x).strip()],
        "location": str(ev.get("location") or "").strip(),
        "time_hint": str(ev.get("time_hint") or "").strip(),
        "cause": str(ev.get("cause") or "").strip(),
        "process": str(ev.get("process") or "").strip(),
        "result": str(ev.get("result") or "").strip(),
        "importance": _float(ev.get("importance"), 0.0),
        "visual_score": _float(ev.get("visual_score"), 0.0),
        "evidence": str(ev.get("evidence") or "").strip(),
    }


def build_timeline(chunks_meta: list[dict], extracts: dict[tuple[str, str], dict]) -> list[dict]:
    """Flatten per-chunk events into a timeline with full fact fields."""
    ordered = sorted(chunks_meta, key=lambda c: (c["chapter_id"], c["index"]))
    events: list[dict] = []
    seen: set[str] = set()
    n = 1
    for c in ordered:
        key = (c["chapter_id"], c["id"])
        for ev in extracts.get(key, {}).get("events", []):
            summary = (
                str(ev.get("summary") or ev.get("description") or ev.get("text") or "")
                .strip()
            )
            if not summary:
                continue
            norm = _norm_summary(summary)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            fields = _event_fields(ev if isinstance(ev, dict) else {})
            events.append(
                {
                    "id": f"event_{n:04d}",
                    "chapter_id": c["chapter_id"],
                    "chunk_id": c.get("chunk_id") or c["id"],
                    "chunk_local_id": c["id"],
                    "narrative_order": n,
                    "summary": summary,
                    **fields,
                    "raw": ev,
                }
            )
            n += 1
    return events


def write_timeline_pages(
    events: list[dict],
    *,
    page_size: int = 50,
    pages_dir: Path,
    index_json: Path,
) -> dict:
    page_size = max(1, int(page_size or 50))
    pages_dir.mkdir(parents=True, exist_ok=True)
    for old in pages_dir.glob("p*.json"):
        old.unlink()
    pages = []
    total = len(events)
    page_count = max(1, (total + page_size - 1) // page_size) if total else 0
    for page in range(page_count):
        start = page * page_size
        chunk = events[start : start + page_size]
        path = pages_dir / f"p{page + 1:04d}.json"
        path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        pages.append(
            {
                "page": page + 1,
                "offset": start,
                "count": len(chunk),
                "path": path.name,
            }
        )
    index = {
        "total_count": total,
        "page_size": page_size,
        "page_count": page_count,
        "pages": pages,
    }
    index_json.parent.mkdir(parents=True, exist_ok=True)
    index_json.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def run_timeline(
    chunks_jsonl: Path,
    extract_dir: Path,
    out_json: Path,
    *,
    enriched_json: Path | None = None,
    page_size: int = 50,
    pages_dir: Path | None = None,
    index_json: Path | None = None,
) -> list[dict]:
    if enriched_json is not None and enriched_json.exists():
        events = json.loads(enriched_json.read_text(encoding="utf-8"))
        events = _dedupe_event_list(events)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if pages_dir is not None and index_json is not None:
            write_timeline_pages(
                events, page_size=page_size, pages_dir=pages_dir, index_json=index_json
            )
        return events

    chunks_meta = [
        json.loads(l)
        for l in chunks_jsonl.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    extracts: dict[tuple[str, str], dict] = {}
    for path in extract_dir.glob("*/*.json"):
        extracts[(path.parent.name, path.stem)] = json.loads(
            path.read_text(encoding="utf-8")
        )
    events = build_timeline(chunks_meta, extracts)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    if pages_dir is not None and index_json is not None:
        write_timeline_pages(
            events, page_size=page_size, pages_dir=pages_dir, index_json=index_json
        )
    return events


def _promote_enriched(ev: dict) -> dict:
    raw = ev.get("raw") if isinstance(ev.get("raw"), dict) else {}
    fields = _event_fields({**raw, **ev})
    item = dict(ev)
    item.update(fields)
    if not item.get("summary"):
        item["summary"] = str(ev.get("summary") or "").strip()
    return item


def _dedupe_event_list(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    n = 1
    for ev in events:
        summary = str(ev.get("summary") or "").strip()
        norm = _norm_summary(summary)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        item = _promote_enriched(ev)
        item["id"] = f"event_{n:04d}"
        item["narrative_order"] = n
        item["summary"] = summary
        out.append(item)
        n += 1
    return out
