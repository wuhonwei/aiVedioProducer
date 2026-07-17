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
    assert p.metadata_json == p.clean_metadata_json
    assert p.metadata_json.name == "metadata.json"
    assert p.clean_report_json.name == "clean_report.json"
    assert p.chapter_report_json.name == "chapter_report.json"
    assert p.chunk_report_json.name == "chunk_report.json"
    assert p.extract_report_json.name == "extract_report.json"
    assert p.extract_errors_json.name == "errors.json"
    assert p.normalize_report_json.name == "normalize_report.json"
    assert p.candidate_pairs_json.name == "candidate_pairs.json"
    assert p.uncertain_entities_json.name == "uncertain_entities.json"
