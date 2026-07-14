from pathlib import Path

from aivp.pipeline.clean import clean_text, run_clean


def test_clean_text_normalizes_newlines_and_bom():
    raw = "\ufeff甲\r\n\r\n\r\n乙\r\n"
    assert clean_text(raw) == "甲\n\n乙\n"


def test_run_clean_writes_file(tmp_path: Path):
    src = tmp_path / "source.txt"
    out = tmp_path / "cleaned.txt"
    src.write_text("\ufeff章一\r\n\r\n内容", encoding="utf-8")
    run_clean(src, out)
    assert out.read_text(encoding="utf-8") == "章一\n\n内容\n"
