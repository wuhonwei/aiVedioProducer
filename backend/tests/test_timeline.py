from aivp.pipeline.timeline import build_timeline, _dedupe_event_list


def test_timeline_orders_by_chapter_then_index():
    chunks_meta = [
        {"id": "0001", "chunk_id": "chapter_0001_chunk_0001", "chapter_id": "chapter_0001", "index": 1},
        {"id": "0001", "chunk_id": "chapter_0002_chunk_0001", "chapter_id": "chapter_0002", "index": 1},
    ]
    extracts = {
        ("chapter_0001", "0001"): {
            "events": [
                {
                    "summary": "相遇",
                    "participants": ["甲"],
                    "location": "渡口",
                    "cause": "赶路",
                    "result": "见面",
                    "importance": 0.8,
                    "visual_score": 0.9,
                    "evidence": "甲在渡口遇见乙。",
                }
            ]
        },
        ("chapter_0002", "0001"): {"events": [{"summary": "决裂"}]},
    }
    events = build_timeline(chunks_meta, extracts)
    assert [e["summary"] for e in events] == ["相遇", "决裂"]
    assert events[0]["id"] == "event_0001"
    assert events[0]["participants"] == ["甲"]
    assert events[0]["location"] == "渡口"
    assert events[0]["cause"] == "赶路"
    assert events[0]["result"] == "见面"
    assert events[0]["evidence"]
    assert events[0]["visual_score"] == 0.9
    assert events[0]["legacy_chunk_id"] == "0001"
    assert events[0]["chunk_local_id"] == "0001"
    assert "story_time_hint" in events[0]
    assert events[0]["is_flashback"] is False


def test_timeline_dedupes_exact_and_whitespace_duplicates():
    chunks_meta = [
        {"id": "0001", "chapter_id": "chapter_0001", "index": 1},
        {"id": "0002", "chapter_id": "chapter_0001", "index": 2},
        {"id": "0001", "chapter_id": "chapter_0002", "index": 1},
    ]
    same = "林砚之抵达青川渡寻找陈守义"
    extracts = {
        ("chapter_0001", "0001"): {"events": [{"summary": same}]},
        ("chapter_0001", "0002"): {"events": [{"summary": f"  {same}  "}]},
        ("chapter_0002", "0001"): {"events": [{"summary": same}, {"summary": "夜路回城"}]},
    }
    events = build_timeline(chunks_meta, extracts)
    summaries = [e["summary"] for e in events]
    assert summaries.count(same) == 1
    assert "夜路回城" in summaries
    assert len(events) == 2


def test_dedupe_event_list_renumbers():
    events = _dedupe_event_list(
        [
            {"id": "event_0001", "summary": "A", "location": "庙"},
            {"id": "event_0002", "summary": "A"},
            {"id": "event_0003", "summary": "B"},
        ]
    )
    assert [e["summary"] for e in events] == ["A", "B"]
    assert events[0]["id"] == "event_0001"
    assert events[0]["location"] == "庙"
    assert events[1]["id"] == "event_0002"
