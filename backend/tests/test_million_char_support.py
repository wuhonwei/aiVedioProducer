"""Long-form pipeline smoke tests for million-char Plan A."""
from __future__ import annotations

import json
from pathlib import Path

from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.pipeline.assemble import assemble_bible, synthesize_volume_synopsis
from aivp.pipeline.extract import run_extract
from aivp.pipeline.normalize import merge_volume_entities, run_normalize_volume
from aivp.pipeline.timeline import run_timeline, write_timeline_pages
from aivp.pipeline.volumes import plan_volumes


def _fake_extract_default():
    return {
        "summary": "一段剧情",
        "characters": [{"name": "李青云", "aliases": [], "evidence": "李青云"}],
        "locations": [{"name": "青云山", "aliases": [], "evidence": "青云山"}],
        "factions": [],
        "props": [],
        "events": [{"summary": "李青云上山修炼", "evidence": "李青云上山修炼"}],
        "foreshadowing": [],
        "relationships": [],
        "visual_cues": [],
        "visual_candidates": [],
        "voice_cues": [],
        "adaptation_notes": [],
    }


def test_extract_parallel_many_chunks(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "long_extract")
    paths.ensure()
    rows = []
    for i in range(120):
        rows.append(
            {
                "id": f"{i+1:04d}",
                "chapter_id": f"ch{(i // 10) + 1:03d}",
                "chapter_title": "T",
                "text": f"李青云在青云山修炼第{i}日。",
                "index": i + 1,
            }
        )
    paths.chunks_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    llm = FakeLlm(default=_fake_extract_default())
    result = run_extract(
        paths,
        llm,
        max_retries=0,
        skip_bad=True,
        workers=4,
        progress_every=10,
    )
    assert result["done"] == 120
    assert result["report"]["workers"] == 4
    written = list(paths.extract_dir.glob("*/*.json"))
    assert len(written) == 120


def test_volume_normalize_merge(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "vol_merge")
    paths.ensure()
    for ch, names in (("ch001", ["甲", "乙"]), ("ch002", ["乙", "丙"])):
        d = paths.extract_dir / ch
        d.mkdir(parents=True, exist_ok=True)
        payload = _fake_extract_default()
        payload["characters"] = [
            {"name": n, "aliases": [], "evidence": n} for n in names
        ]
        (d / "0001.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    e1 = run_normalize_volume(paths.extract_dir, paths.volume_entities_json("vol001"), ["ch001"])
    e2 = run_normalize_volume(paths.extract_dir, paths.volume_entities_json("vol002"), ["ch002"])
    merged = merge_volume_entities([e1, e2])
    names = {c["name"] for c in merged["entities"]["characters"]}
    assert "甲" in names and "乙" in names and "丙" in names


def test_timeline_pagination_files(tmp_path: Path):
    events = [{"id": f"evt{i:04d}", "summary": f"e{i}"} for i in range(1, 121)]
    pages_dir = tmp_path / "pages"
    index_json = tmp_path / "timeline_index.json"
    index = write_timeline_pages(
        events, page_size=50, pages_dir=pages_dir, index_json=index_json
    )
    assert index["total_count"] == 120
    assert index["page_count"] == 3
    assert (pages_dir / "p0001.json").exists()
    page1 = json.loads((pages_dir / "p0001.json").read_text(encoding="utf-8"))
    assert len(page1) == 50


def test_layered_synth_uses_volume_synopses():
    volumes = plan_volumes(
        [
            {"id": f"ch{i:03d}", "title": f"第{i}章", "char_count": 50_000, "text": "x" * 10}
            for i in range(1, 5)
        ],
        max_chars=80_000,
        max_chapters=40,
    )
    assert len(volumes) >= 2
    events = [
        {"id": f"evt{i:04d}", "chapter_id": f"ch{((i - 1) // 30) + 1:03d}", "summary": f"事件{i}"}
        for i in range(1, 121)
    ]
    chapters = [{"id": f"ch{i:03d}", "title": f"第{i}章"} for i in range(1, 5)]
    synopses = [
        synthesize_volume_synopsis(
            None, volume=v, chapters=chapters, events=events
        )
        for v in volumes
    ]
    assert len(synopses) == len(volumes)
    assert all(s.get("synopsis") for s in synopses)
    # Tail events (high ids) must be covered by later volumes, not dropped by [:80]
    covered_chapters = set()
    for s in synopses:
        covered_chapters.update(s.get("chapter_ids") or [])
    assert "ch004" in covered_chapters

    bible = assemble_bible(
        project_name="长测",
        chapters=chapters,
        entities={"characters": [], "locations": [], "factions": [], "props": []},
        events=events,
        arcs=[],
        extracts=[],
        volume_synopses=synopses,
        timeline_page_size=50,
    )
    assert bible["timeline_ref"]["total_count"] == 120
    assert len(bible["timeline"]) == 50
    assert bible["source_stats"]["volume_count"] == len(volumes)


def test_run_timeline_writes_pages(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "tl")
    paths.ensure()
    events = [{"id": f"evt{i:04d}", "summary": f"s{i}", "chapter_id": "ch001"} for i in range(1, 60)]
    paths.events_enriched_json.write_text(
        json.dumps(events, ensure_ascii=False), encoding="utf-8"
    )
    # create empty chunks so path exists (enriched path short-circuits)
    paths.chunks_jsonl.write_text("", encoding="utf-8")
    out = run_timeline(
        paths.chunks_jsonl,
        paths.extract_dir,
        paths.events_json,
        enriched_json=paths.events_enriched_json,
        page_size=50,
        pages_dir=paths.timeline_pages_dir,
        index_json=paths.timeline_index_json,
    )
    assert len(out) == 59
    assert paths.timeline_index_json.exists()
    index = json.loads(paths.timeline_index_json.read_text(encoding="utf-8"))
    assert index["total_count"] == 59
