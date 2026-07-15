from aivp.pipeline.arcs import build_arcs


def test_build_arcs_groups_by_chapter():
    chapters = [{"id": "ch001", "title": "第一章 开端"}, {"id": "ch002", "title": "第二章 高潮"}]
    events = [
        {"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"},
        {"id": "evt0002", "chapter_id": "ch002", "summary": "决裂"},
    ]
    arcs = build_arcs(chapters, events)
    assert len(arcs) == 2
    assert arcs[0]["chapter_id"] == "ch001"
    assert "相遇" in arcs[0]["summary"]


def test_build_arcs_prefers_extract_summaries():
    chapters = [{"id": "ch001", "title": "第一章 雾锁渡口"}]
    events = [
        {"chapter_id": "ch001", "summary": "林砚之找陈守义求助"},
        {"chapter_id": "ch001", "summary": "苏晚卿往事被提及"},
    ]
    extracts = {
        "ch001": [
            "林砚之来到青川渡，找到陈守义，并得知母亲苏晚卿的往事。",
        ]
    }
    arcs = build_arcs(chapters, events, extract_summaries_by_chapter=extracts)
    assert "青川渡" in arcs[0]["summary"]
    assert "苏晚卿" in arcs[0]["summary"]
    assert arcs[0]["extract_summary_count"] == 1
    # extract overview should lead; thin event-only phrasing alone is insufficient
    assert len(arcs[0]["summary"]) > len("；".join(e["summary"] for e in events))
