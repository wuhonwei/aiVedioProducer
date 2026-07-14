from aivp.pipeline.chapters import split_chapters

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
