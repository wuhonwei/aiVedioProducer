from aivp.pipeline.timeline import build_timeline


def test_timeline_orders_by_chapter_then_index():
    chunks_meta = [
        {"id": "0001", "chapter_id": "ch001", "index": 1},
        {"id": "0001", "chapter_id": "ch002", "index": 1},
    ]
    extracts = {
        ("ch001", "0001"): {"events": [{"summary": "相遇"}]},
        ("ch002", "0001"): {"events": [{"summary": "决裂"}]},
    }
    events = build_timeline(chunks_meta, extracts)
    assert [e["summary"] for e in events] == ["相遇", "决裂"]
    assert events[0]["id"] == "evt0001"
