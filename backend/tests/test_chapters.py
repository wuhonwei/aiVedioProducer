from aivp.pipeline.chapters import chapter_report, split_chapters

SAMPLE = """第一章 山雨欲来

正文甲。

第二章 夜宴

正文乙。
"""


def test_split_chapters_by_cn_heading():
    chapters = split_chapters(SAMPLE)
    assert len(chapters) == 2
    assert chapters[0]["id"] == "ch001"
    assert chapters[0]["title"] == "第一章 山雨欲来"
    assert "正文甲" in chapters[0]["text"]
    assert chapters[1]["title"] == "第二章 夜宴"
    assert chapters[0]["start_offset"] == 0
    assert chapters[0]["char_count"] == len(chapters[0]["text"])


def test_split_prologue_and_chapter_english():
    text = "楔子\n开场。\n\nChapter 1 Rain\nBody.\n"
    chapters = split_chapters(text)
    assert len(chapters) >= 2
    assert chapters[0]["title"].startswith("楔子")


def test_chapter_report_marks_short():
    chapters = [
        {
            "id": "ch001",
            "char_count": 50,
            "text": "短",
        }
    ]
    rep = chapter_report(chapters)
    assert rep["suspicious_chapters"][0]["reason"] == "too_short"
