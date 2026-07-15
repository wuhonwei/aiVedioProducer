from aivp.pipeline.chunks import chunk_chapters


def test_chunk_respects_size_and_overlap():
    chapters = [
        {
            "id": "ch001",
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
    assert chunks[0]["chapter_id"] == "ch001"
    assert chunks[0]["id"] == "0001"
    assert chunks[0]["chunk_id"] == "ch001_chunk_0001"
    assert len(chunks[0]["text"]) <= 1200
    assert chunks[1]["text"][:50] in chunks[0]["text"]
    assert chunks[0]["next_chunk_id"] == chunks[1]["chunk_id"]
    assert chunks[1]["prev_chunk_id"] == chunks[0]["chunk_id"]
    assert "start_offset" in chunks[0]
    assert "end_offset" in chunks[0]
