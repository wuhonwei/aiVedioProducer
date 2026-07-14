from pathlib import Path

from aivp.paths import ProjectPaths


def test_project_paths_layout(tmp_path: Path):
    p = ProjectPaths(tmp_path, "proj1")
    p.ensure()
    assert p.source_txt.exists() is False
    assert p.raw_dir.is_dir()
    assert p.stages_dir.is_dir()
    assert p.overlay_json.name == "story_bible.overlay.json"
    assert p.auto_bible_json.name == "story_bible.auto.json"
    assert "01_clean" in str(p.clean_txt)
    assert p.extract_chunk_json("ch01", "0001").parent.name == "ch01"
