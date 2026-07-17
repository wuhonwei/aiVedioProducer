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
    result = run_extract(paths, llm, max_retries=1, skip_bad=True)
    out = paths.extract_chunk_json("ch001", "0001")
    assert out.exists()
    assert paths.extract_report_json.exists()
    assert paths.extract_errors_json.exists()
    report = json.loads(paths.extract_report_json.read_text(encoding="utf-8"))
    assert report["total"] == 1
    assert report["succeeded"] == 1
    assert report["failed"] == 0
    assert "retry_count_total" in report
    assert result["report"]["succeeded"] == 1


class _BoomLlm(FakeLlm):
    def complete_json(self, system, user, *, should_cancel=None):  # noqa: ANN001
        raise RuntimeError("boom")


def test_run_extract_writes_structured_errors(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p2")
    paths.ensure()
    chunk = {
        "id": "0002",
        "chapter_id": "chapter_0003",
        "chapter_title": "T",
        "text": "乙",
        "chunk_id": "chapter_0003_chunk_0002",
    }
    paths.chunks_jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    run_extract(paths, _BoomLlm(), max_retries=1, skip_bad=True)
    errors = json.loads(paths.extract_errors_json.read_text(encoding="utf-8"))
    assert len(errors) == 1
    err = errors[0]
    assert err["chunk_id"] == "chapter_0003_chunk_0002"
    assert err["legacy_chunk_id"] == "0002"
    assert err["chapter_id"] == "chapter_0003"
    assert err["error_type"] == "schema_validation_error"
    assert err["skipped"] is True
    assert err["retry_count"] >= 1
    report = json.loads(paths.extract_report_json.read_text(encoding="utf-8"))
    assert report["failed"] == 1
    assert report["retry_count_total"] >= 1
    assert report["errors"]
