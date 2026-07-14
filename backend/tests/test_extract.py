from pathlib import Path
import json
from aivp.llm.fake import FakeLlm
from aivp.pipeline.extract import extract_chunk, run_extract
from aivp.paths import ProjectPaths


def test_extract_chunk_validates_schema():
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山"}],
        "factions": [],
        "props": [],
        "events": [{"summary": "比武"}],
        "foreshadowing": [],
        "visual_cues": ["水墨远山"],
        "voice_cues": [],
        "adaptation_notes": [],
    })
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "第一章", "text": "李青云在青云山比武。"}
    result = extract_chunk(chunk, llm)
    assert result["characters"][0]["name"] == "李青云"


def test_run_extract_writes_files(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "T", "text": "甲"}
    paths.chunks_jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    llm = FakeLlm(default={
        "characters": [], "locations": [], "factions": [], "props": [],
        "events": [], "foreshadowing": [], "visual_cues": [], "voice_cues": [],
        "adaptation_notes": [],
    })
    run_extract(paths, llm, max_retries=1, skip_bad=True)
    out = paths.extract_chunk_json("ch001", "0001")
    assert out.exists()
