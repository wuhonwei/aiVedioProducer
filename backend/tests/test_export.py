from pathlib import Path
from aivp.bible.export_md import export_version


def test_export_writes_json_and_md(tmp_path: Path):
    bible = {"project_meta": {"title": "测"}, "logline": "一句话", "warnings": []}
    # fill required keys minimally
    for k in [
        "worldbuilding", "plot_structure", "characters", "character_relations", "locations",
        "factions", "props", "timeline", "foreshadowing", "adaptation_notes", "visual_style",
        "character_visuals", "voice_bible", "production_constraints",
    ]:
        bible.setdefault(k, {} if k not in ("characters", "timeline") else [])
    paths = export_version(tmp_path, bible, version=1)
    assert paths["json"].name == "story_bible.v001.json"
    assert "一句话" in paths["md"].read_text(encoding="utf-8")
