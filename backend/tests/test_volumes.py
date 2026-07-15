from aivp.pipeline.volumes import filter_chapters_by_range, plan_volumes


def test_plan_volumes_by_chars():
    chapters = [
        {"id": f"ch{i:03d}", "char_count": 30_000, "start_offset": i * 10, "end_offset": i * 10 + 5}
        for i in range(1, 5)
    ]
    vols = plan_volumes(chapters, max_chars=80_000, max_chapters=40)
    assert len(vols) == 2
    assert vols[0]["chapter_count"] == 3
    assert vols[1]["chapter_count"] == 1
    assert vols[0]["id"] == "vol001"


def test_plan_volumes_by_chapter_cap():
    chapters = [
        {"id": f"ch{i:03d}", "char_count": 100, "start_offset": 0, "end_offset": 1}
        for i in range(1, 45)
    ]
    vols = plan_volumes(chapters, max_chars=1_000_000, max_chapters=40)
    assert len(vols) == 2
    assert vols[0]["chapter_count"] == 40
    assert vols[1]["chapter_count"] == 4


def test_filter_chapter_range():
    chapters = [{"id": f"ch{i:03d}"} for i in range(1, 6)]
    subset = filter_chapters_by_range(chapters, chapter_from="ch002", chapter_to="ch004")
    assert [c["id"] for c in subset] == ["ch002", "ch003", "ch004"]
