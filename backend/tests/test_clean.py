from pathlib import Path

from aivp.pipeline.clean import clean_text, run_clean


def test_clean_text_normalizes_newlines_and_bom():
    raw = "\ufeff甲\r\n\r\n\r\n乙\r\n"
    cleaned, report = clean_text(raw)
    assert cleaned == "甲\n\n乙\n"
    assert report["normalized_newlines"] is True


def test_clean_removes_url_and_ad_lines():
    raw = "正文\nhttps://spam.example/x\n请收藏本站免费看\n继续\n"
    cleaned, report = clean_text(raw)
    assert "正文" in cleaned
    assert "继续" in cleaned
    assert "https://" not in cleaned
    assert report["removed_url_lines"] >= 1
    assert report["removed_ad_lines"] >= 1


def test_run_clean_writes_file_and_reports(tmp_path: Path):
    src = tmp_path / "source.txt"
    out = tmp_path / "cleaned.txt"
    src.write_text("\ufeff章一\r\n\r\n内容", encoding="utf-8")
    run_clean(src, out)
    assert out.read_text(encoding="utf-8") == "章一\n\n内容\n"
    meta = (out.parent / "metadata.json").read_text(encoding="utf-8")
    assert "detected_encoding" in meta
    report = (out.parent / "clean_report.json").read_text(encoding="utf-8")
    assert "removed_lines" in report
