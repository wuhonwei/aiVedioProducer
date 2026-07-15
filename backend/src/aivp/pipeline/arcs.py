import json
import re
from pathlib import Path

_STRIP = re.compile(r"\s+")
_PUNCT = re.compile(r'[，。！？、；：:“”"\'（）()【】\[\]…—\-·,.]+')


def _norm(text: str) -> str:
    return _PUNCT.sub("", _STRIP.sub("", (text or "").strip()))


def _uniq_join(parts: list[str], *, sep: str = "；", limit: int = 12) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        text = (p or "").strip()
        if not text:
            continue
        key = _norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return sep.join(out)


def build_arcs(
    chapters: list[dict],
    events: list[dict],
    *,
    extract_summaries_by_chapter: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Build per-chapter arcs.

    Prefer chunk extract summaries (richer narrative) and append event beats
    that are not already covered, so early chapters are not just two short events.
    """
    by_ch_events: dict[str, list[str]] = {}
    for e in events:
        cid = e.get("chapter_id")
        if not cid:
            continue
        by_ch_events.setdefault(str(cid), []).append(str(e.get("summary") or ""))

    extract_map = extract_summaries_by_chapter or {}
    arcs = []
    for ch in chapters:
        cid = ch["id"]
        extracts = [str(s) for s in extract_map.get(cid, []) if str(s).strip()]
        event_sums = [str(s) for s in by_ch_events.get(cid, []) if str(s).strip()]

        if extracts:
            # Extract chunk summaries already follow reading order and often span
            # the whole chapter. Do not append timeline one-liners after them —
            # that puts mid-chapter beats after an ending that the extract already stated.
            summary = _uniq_join(extracts, limit=10)
        else:
            summary = _uniq_join(event_sums, limit=12)

        arcs.append(
            {
                "id": f"arc_{cid}",
                "chapter_id": cid,
                "title": ch["title"],
                "summary": summary,
                "extract_summary_count": len(extracts),
                "event_count": len(event_sums),
            }
        )
    return arcs


def load_extract_summaries(extract_dir: Path) -> dict[str, list[str]]:
    by_ch: dict[str, list[str]] = {}
    if not extract_dir.exists():
        return by_ch
    for path in sorted(extract_dir.glob("*/*.json")):
        if path.name in {"extract_report.json", "errors.json", "low_quality_chunks.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = str(data.get("summary") or "").strip()
        if not summary:
            continue
        by_ch.setdefault(path.parent.name, []).append(summary)
    return by_ch


def run_arcs(
    chapters_json: Path,
    events_json: Path,
    out_json: Path,
    *,
    extract_dir: Path | None = None,
) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    events = json.loads(events_json.read_text(encoding="utf-8"))
    extract_map = load_extract_summaries(extract_dir) if extract_dir is not None else {}
    arcs = build_arcs(chapters, events, extract_summaries_by_chapter=extract_map)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(arcs, ensure_ascii=False, indent=2), encoding="utf-8")
    return arcs
