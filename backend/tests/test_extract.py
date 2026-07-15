from pathlib import Path
import json
from aivp.llm.fake import FakeLlm
from aivp.pipeline.extract import extract_chunk, run_extract
from aivp.paths import ProjectPaths


def test_extract_chunk_validates_schema():
    llm = FakeLlm(default={
        "summary": "比武",
        "characters": [{"name": "李青云", "aliases": ["青云"], "evidence": "李青云出剑"}],
        "locations": [{"name": "青云山", "evidence": "青云山巅"}],
        "factions": [],
        "props": [],
        "events": [{"summary": "比武", "evidence": "比武开始"}],
        "foreshadowing": [],
        "relationships": [],
        "visual_cues": ["水墨远山"],
        "visual_candidates": [],
        "voice_cues": [],
        "adaptation_notes": [],
    })
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "第一章", "text": "李青云在青云山比武。"}
    result = extract_chunk(chunk, llm)
    assert result["characters"][0]["name"] == "李青云"
    assert "quality" in result


def test_run_extract_writes_files_and_report(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "T", "text": "甲", "chunk_id": "ch001_chunk_0001"}
    paths.chunks_jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    llm = FakeLlm(default={
        "summary": "",
        "characters": [], "locations": [], "factions": [], "props": [],
        "events": [], "foreshadowing": [], "relationships": [],
        "visual_cues": [], "visual_candidates": [], "voice_cues": [],
        "adaptation_notes": [],
    })
    run_extract(paths, llm, max_retries=1, skip_bad=True)
    out = paths.extract_chunk_json("ch001", "0001")
    assert out.exists()
    assert paths.extract_report_json.exists()
    assert paths.extract_errors_json.exists()
