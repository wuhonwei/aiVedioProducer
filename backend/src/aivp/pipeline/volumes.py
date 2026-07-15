"""Plan novel volumes for million-char pipelines."""
from __future__ import annotations

import json
from pathlib import Path


DEFAULT_MAX_CHARS = 80_000
DEFAULT_MAX_CHAPTERS = 40


def plan_volumes(
    chapters: list[dict],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_chapters: int = DEFAULT_MAX_CHAPTERS,
) -> list[dict]:
    """Split chapters into volumes by char budget or chapter count (whichever first)."""
    if not chapters:
        return []
    volumes: list[dict] = []
    buf: list[dict] = []
    buf_chars = 0
    for ch in chapters:
        n = int(ch.get("char_count") or len(ch.get("text") or ""))
        buf.append(ch)
        buf_chars += n
        if buf_chars >= max_chars or len(buf) >= max_chapters:
            volumes.append(_make_volume(len(volumes) + 1, buf))
            buf = []
            buf_chars = 0
    if buf:
        volumes.append(_make_volume(len(volumes) + 1, buf))
    return volumes


def _make_volume(index: int, chapters: list[dict]) -> dict:
    starts = [int(c.get("start_offset") or 0) for c in chapters]
    ends = [int(c.get("end_offset") or 0) for c in chapters]
    char_count = sum(int(c.get("char_count") or len(c.get("text") or "")) for c in chapters)
    return {
        "id": f"vol{index:03d}",
        "index": index,
        "chapter_ids": [c["id"] for c in chapters],
        "start_offset": min(starts) if starts else 0,
        "end_offset": max(ends) if ends else 0,
        "char_count": char_count,
        "chapter_count": len(chapters),
    }


def run_plan_volumes(
    chapters_json: Path,
    out_json: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_chapters: int = DEFAULT_MAX_CHAPTERS,
) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    volumes = plan_volumes(chapters, max_chars=max_chars, max_chapters=max_chapters)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "volume_count": len(volumes),
        "max_chars": max_chars,
        "max_chapters": max_chapters,
        "volumes": volumes,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return volumes


def filter_chapters_by_volume(chapters: list[dict], volume: dict) -> list[dict]:
    ids = set(volume.get("chapter_ids") or [])
    return [c for c in chapters if c.get("id") in ids]


def filter_chapters_by_range(
    chapters: list[dict],
    *,
    chapter_from: str | None = None,
    chapter_to: str | None = None,
) -> list[dict]:
    if not chapter_from and not chapter_to:
        return chapters
    ids = [c["id"] for c in chapters]
    start = ids.index(chapter_from) if chapter_from and chapter_from in ids else 0
    end = ids.index(chapter_to) if chapter_to and chapter_to in ids else len(ids) - 1
    if start > end:
        start, end = end, start
    keep = set(ids[start : end + 1])
    return [c for c in chapters if c["id"] in keep]
