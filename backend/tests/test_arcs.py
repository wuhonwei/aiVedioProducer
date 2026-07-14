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
