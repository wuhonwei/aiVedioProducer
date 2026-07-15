from aivp.pipeline.timeline import build_timeline, _dedupe_event_list


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


def test_timeline_dedupes_exact_and_whitespace_duplicates():
    chunks_meta = [
        {"id": "0001", "chapter_id": "ch001", "index": 1},
        {"id": "0002", "chapter_id": "ch001", "index": 2},
        {"id": "0001", "chapter_id": "ch002", "index": 1},
    ]
    same = "林砚之抵达青川渡寻找陈守义"
    extracts = {
        ("ch001", "0001"): {"events": [{"summary": same}]},
        ("ch001", "0002"): {"events": [{"summary": f"  {same}  "}]},
        ("ch002", "0001"): {"events": [{"summary": same}, {"summary": "夜路回城"}]},
    }
    events = build_timeline(chunks_meta, extracts)
    summaries = [e["summary"] for e in events]
    assert summaries.count(same) == 1
    assert "夜路回城" in summaries
    assert len(events) == 2


def test_dedupe_event_list_renumbers():
    events = _dedupe_event_list(
        [
            {"id": "evt0001", "summary": "A"},
            {"id": "evt0002", "summary": "A"},
            {"id": "evt0003", "summary": "B"},
        ]
    )
    assert [e["summary"] for e in events] == ["A", "B"]
    assert events[1]["id"] == "evt0002"
