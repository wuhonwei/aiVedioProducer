from pathlib import Path

from aivp.bible.export_md import export_markdown_pack, export_version
from aivp.bible.meta import ensure_bible_meta, set_block_lock, set_block_review


def test_bible_meta_review_and_lock():
    meta = ensure_bible_meta(None)
    assert "logline" in meta["blocks"]
    meta = set_block_review(meta, block="logline", action="approve", note="ok")
    assert meta["blocks"]["logline"]["review_status"] == "approved"
    meta = set_block_lock(meta, block="logline", locked=True)
    assert meta["blocks"]["logline"]["locked"] is True


def test_export_pack(tmp_path: Path):
    bible = {"schema_version": 3, "logline": "一句话", "characters": []}
    paths = export_version(tmp_path, bible, 1)
    assert paths["json"].exists()
    assert paths["md"].exists()
    assert paths["pack"].exists()
    assert (paths["pack"] / "01_logline_and_theme.md").exists()
    assert (paths["pack"] / "json" / "story_bible.merged.json").exists()
    export_markdown_pack(tmp_path / "pack2", bible)
