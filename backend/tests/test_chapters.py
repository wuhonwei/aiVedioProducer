from aivp.pipeline.chapters import chapter_report, split_chapters

SAMPLE = """第一章 山雨欲来

正文甲。

第二章 夜宴

正文乙。
"""


def test_split_chapters_by_cn_heading():
    chapters = split_chapters(SAMPLE)
    assert len(chapters) == 2
    assert chapters[0]["id"] == "chapter_0001"
    assert chapters[0]["chapter_id"] == "chapter_0001"
    assert chapters[0]["legacy_id"] == "ch001"
    assert chapters[0]["title"] == "第一章 山雨欲来"
    assert "正文甲" in chapters[0]["text"]
    assert chapters[1]["title"] == "第二章 夜宴"
    assert chapters[0]["start_offset"] == 0
    assert chapters[0]["char_count"] == len(chapters[0]["text"])


def test_split_prologue_and_chapter_english():
    text = "楔子\n开场。\n\nChapter 1 Rain\nBody.\n\n后记\n收尾。\n"
    chapters = split_chapters(text)
    assert len(chapters) >= 3
    assert chapters[0]["title"].startswith("楔子")
    assert any(c["title"].startswith("后记") for c in chapters)


def test_split_hui_volume_and_untitled():
    text = "第十七回 夜走\n甲\n\n卷一 起\n乙\n\n第1章\n丙\n"
    chapters = split_chapters(text)
    titles = [c["title"] for c in chapters]
    assert any("回" in t for t in titles)
    assert any(t.startswith("卷") for t in titles)
    assert any(t.startswith("第1章") for t in titles)


def test_chapter_report_marks_short():
    chapters = [
        {
            "id": "chapter_0001",
            "chapter_id": "chapter_0001",
            "char_count": 50,
            "text": "短",
        }
    ]
    rep = chapter_report(chapters)
    assert any(s["reason"] == "too_short" for s in rep["suspicious_chapters"])


def test_unsplit_fallback_and_report():
    chapters = split_chapters("没有章节标题的长文。" * 20)
    assert len(chapters) == 1
    assert chapters[0]["maybe_unsplit"] is True
    assert chapters[0]["legacy_id"] == "ch001"
    rep = chapter_report(chapters)
    assert rep["maybe_unsplit"] is True
    assert "maybe_unsplit" in rep["warnings"]
