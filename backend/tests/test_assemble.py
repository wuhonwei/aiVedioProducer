from aivp.pipeline.assemble import assemble_bible
from aivp.schemas import REQUIRED_BIBLE_KEYS


def test_assemble_includes_all_16_keys():
    bible = assemble_bible(
        project_name="测书",
        chapters=[{"id": "ch001", "title": "第一章", "text": "甲"}],
        entities={"characters": [{"id": "ent_0001", "name": "李青云", "aliases": []}], "locations": [], "factions": [], "props": []},
        events=[{"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"}],
        arcs=[{"id": "arc_ch001", "chapter_id": "ch001", "title": "第一章", "summary": "相遇"}],
        extracts=[{"foreshadowing": [{"note": "剑冢"}], "visual_cues": ["水墨"], "voice_cues": ["低沉男声"], "adaptation_notes": ["开场冷开"]}],
        warnings=["skip:ch001/0002"],
    )
    for k in REQUIRED_BIBLE_KEYS:
        assert k in bible
    assert bible["characters"][0]["name"] == "李青云"
    assert bible["warnings"] == ["skip:ch001/0002"]
