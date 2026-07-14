from aivp.llm.fake import FakeLlm
from aivp.pipeline.assemble import assemble_bible
from aivp.schemas import REQUIRED_BIBLE_KEYS


def test_assemble_includes_all_16_keys():
    bible = assemble_bible(
        project_name="测书",
        chapters=[{"id": "ch001", "title": "第一章", "text": "甲"}],
        entities={
            "characters": [{"id": "ent_0001", "name": "李青云", "aliases": []}],
            "locations": [{"id": "loc_1", "name": "青云山", "aliases": []}],
            "factions": [{"id": "fac_1", "name": "天机阁", "aliases": []}],
            "props": [],
        },
        events=[{"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"}],
        arcs=[{"id": "arc_ch001", "chapter_id": "ch001", "title": "第一章", "summary": "相遇"}],
        extracts=[
            {
                "foreshadowing": [{"note": "剑冢"}],
                "visual_cues": ["水墨"],
                "voice_cues": ["低沉男声"],
                "adaptation_notes": ["开场冷开"],
            }
        ],
        warnings=["skip:ch001/0002"],
    )
    for k in REQUIRED_BIBLE_KEYS:
        assert k in bible
    assert bible["characters"][0]["name"] == "李青云"
    assert bible["warnings"] == ["skip:ch001/0002"]
    assert bible["logline"]
    assert bible["worldbuilding"]["summary"]
    assert bible["schema_version"] == 2
    assert bible["source_stats"].get("video_ready") is True


def test_assemble_uses_llm_synth_when_available():
    llm = FakeLlm(
        default={
            "logline": "少年入世，刀光破局。",
            "worldbuilding": {"summary": "山海之间灵气将尽。", "rules": ["灵气稀缺"]},
            "character_relations": [
                {"source": "李青云", "target": "天机阁", "relation": "窥探与防备"}
            ],
            "plot_overview": "入山寻机缘",
        }
    )
    bible = assemble_bible(
        project_name="测书",
        chapters=[{"id": "ch001", "title": "第一章", "text": "甲"}],
        entities={
            "characters": [{"id": "ent_0001", "name": "李青云", "aliases": []}],
            "locations": [],
            "factions": [],
            "props": [],
        },
        events=[{"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"}],
        arcs=[{"id": "arc_ch001", "chapter_id": "ch001", "title": "第一章", "summary": ""}],
        extracts=[],
        llm=llm,
    )
    assert bible["logline"] == "少年入世，刀光破局。"
    assert "灵气将尽" in bible["worldbuilding"]["summary"]
    assert bible["character_relations"][0]["source"] == "李青云"
