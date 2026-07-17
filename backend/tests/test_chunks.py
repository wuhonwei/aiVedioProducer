from pathlib import Path
import json

from aivp.pipeline.chunks import chunk_chapters, chunk_report, run_chunk
import pytest


def test_chunk_respects_size_and_overlap():
    chapters = [
        {
            "id": "chapter_0001",
            "chapter_id": "chapter_0001",
            "legacy_id": "ch001",
            "index": 1,
            "title": "T",
            "text": "字" * 2500,
            "start_offset": 0,
            "heading_start_offset": 0,
            "heading_end_offset": 0,
        }
    ]
    chunks = chunk_chapters(chapters, size=1200, overlap=150)
    assert len(chunks) >= 2
    assert chunks[0]["chapter_id"] == "chapter_0001"
    assert chunks[0]["legacy_chapter_id"] == "ch001"
    assert chunks[0]["id"] == "0001"
    assert chunks[0]["chunk_id"] == "chapter_0001_chunk_0001"
    assert len(chunks[0]["text"]) <= 1200
    assert chunks[1]["text"][:50] in chunks[0]["text"]
    assert chunks[0]["next_chunk_id"] == chunks[1]["chunk_id"]
    assert chunks[1]["prev_chunk_id"] == chunks[0]["chunk_id"]
    assert "start_offset" in chunks[0]
    assert "end_offset" in chunks[0]


def test_overlap_must_be_lt_size():
    with pytest.raises(ValueError, match="overlap_must_be_lt_size"):
        chunk_chapters(
            [{"id": "chapter_0001", "title": "T", "text": "abc", "start_offset": 0}],
            size=100,
            overlap=100,
        )


def test_chunk_report_too_many_chunks():
    chapters = [
        {
            "id": "chapter_0001",
            "title": "长章",
            "text": "字" * 20000,
            "start_offset": 0,
            "heading_start_offset": 0,
            "heading_end_offset": 0,
        }
    ]
    chunks = chunk_chapters(chapters, size=1000, overlap=0)
    rep = chunk_report(chunks, 1000, 0, too_many_chunks_threshold=12)
    assert any(w["reason"] == "too_many_chunks" for w in rep["warnings"])


def test_run_chunk_writes_report(tmp_path: Path):
    chapters = [
        {
            "id": "chapter_0001",
            "legacy_id": "ch001",
            "index": 1,
            "title": "T",
            "text": "正文" * 100,
            "start_offset": 0,
            "heading_start_offset": 0,
            "heading_end_offset": 5,
        }
    ]
    chapters_json = tmp_path / "chapters.json"
    chapters_json.write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "chunks.jsonl"
    report = tmp_path / "chunk_report.json"
    chunks = run_chunk(chapters_json, out, 80, 10, report_json=report)
    assert out.exists()
    assert report.exists()
    assert chunks[0]["chunk_id"] == "chapter_0001_chunk_0001"
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
