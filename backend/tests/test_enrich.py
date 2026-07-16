from pathlib import Path

from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.pipeline.enrich import build_assets, run_enrich
from aivp.pipeline.select_majors import select_majors


def test_build_assets_fills_major_prompt():
    entities = {
        "characters": [{"id": "ent_0001", "name": "林砚之", "aliases": ["少年"]}],
        "locations": [{"id": "loc_1", "name": "青川渡", "aliases": []}],
        "factions": [],
        "props": [{"id": "p1", "name": "玉佩", "aliases": []}],
    }
    majors = {
        "characters": ["ent_0001"],
        "locations": ["loc_1"],
        "factions": [],
        "props": ["p1"],
    }
    llm = FakeLlm(
        default={
            "items": [
                {
                    "name": "林砚之",
                    "appearance": {"face": "清俊微苍"},
                    "wardrobe": {"default": "洗白长衫"},
                    "prompt_zh": "林砚之，清俊微苍，洗白长衫",
                }
            ]
        }
    )
    assets = build_assets(entities, majors, llm, extracts=[])
    lead = assets["characters"][0]
    assert lead["tier"] == "major"
    assert lead["prompt_zh"]
    assert lead["appearance"]["face"]
    assert assets["locations"][0]["prompt_zh"]
    assert assets["props"][0]["prompt_zh"]


def test_build_assets_distinct_without_llm():
    entities = {
        "characters": [
            {
                "id": "ent_0001",
                "name": "林砚之",
                "evidence": "林砚之背着一个半旧的蓝布包袱，站在雾里",
            },
            {
                "id": "ent_0002",
                "name": "苏婆婆",
                "evidence": "白发苍苍的老婆婆，穿着粗布衣衫",
            },
            {
                "id": "ent_0003",
                "name": "周大人",
                "evidence": "穿着官服的人，是县里的知县，周大人",
            },
        ],
        "locations": [],
        "factions": [],
        "props": [],
    }
    majors = {
        "characters": ["ent_0001", "ent_0002", "ent_0003"],
        "locations": [],
        "factions": [],
        "props": [],
    }
    assets = build_assets(entities, majors, llm=None, extracts=[])
    prompts = [c["prompt_zh"] for c in assets["characters"]]
    assert len(set(prompts)) == 3
    wardrobes = [c["wardrobe"]["default"] for c in assets["characters"]]
    assert len(set(wardrobes)) == 3


def test_build_assets_repairs_cloned_llm_looks():
    from aivp.pipeline.character_looks import look_signature

    entities = {
        "characters": [
            {"id": "ent_0001", "name": "甲", "evidence": "甲"},
            {"id": "ent_0002", "name": "乙", "evidence": "乙"},
        ],
        "locations": [],
        "factions": [],
        "props": [],
    }
    majors = {"characters": ["ent_0001", "ent_0002"], "locations": [], "factions": [], "props": []}
    twin = {
        "appearance": {"face": "同脸", "hair": "同发"},
        "wardrobe": {"default": "同衣"},
        "age_look": "青年",
        "prompt_zh": "共用定妆",
    }
    llm = FakeLlm(
        default={
            "items": [
                {"name": "甲", **twin},
                {"name": "乙", **twin},
            ]
        }
    )
    assets = build_assets(entities, majors, llm, extracts=[])
    chars = assets["characters"]
    assert len(chars) == 2
    prompts = [c["prompt_zh"] for c in chars]
    assert len(set(prompts)) == 2
    for card in chars:
        assert "男性" in card["prompt_zh"]
        assert card["appearance"]["body"]
        assert card["appearance"]["eyes"]
        assert card["wardrobe"]["default"]
    assert look_signature(chars[0]) != look_signature(chars[1])


def test_run_enrich_writes_artifacts(tmp_path: Path):
    settings = Settings(data_root=tmp_path)
    paths = ProjectPaths(tmp_path, "e1")
    paths.ensure()
    paths.entities_json.write_text(
        '{"characters":[{"id":"ent_0001","name":"林砚之","aliases":[]}],'
        '"locations":[{"id":"loc_1","name":"青川渡","aliases":[]}],'
        '"factions":[],"props":[]}',
        encoding="utf-8",
    )
    paths.chunks_jsonl.write_text(
        '{"id":"0001","chapter_id":"ch001","index":0,"text":"林砚之到青川渡"}\n',
        encoding="utf-8",
    )
    dest = paths.extract_chunk_json("ch001", "0001")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        '{"characters":[{"name":"林砚之"}],"locations":[{"name":"青川渡"}],'
        '"factions":[],"props":[],"events":[{"summary":"林砚之抵达青川渡"}],'
        '"foreshadowing":[],"visual_cues":["江雾"],"voice_cues":[],"adaptation_notes":[]}',
        encoding="utf-8",
    )
    llm = FakeLlm(default={"items": [], "events": []})
    out = run_enrich(paths, settings, llm, force=True)
    assert paths.assets_json.exists()
    assert paths.events_enriched_json.exists()
    assert out["assets"]["characters"][0]["prompt_zh"]
    assert out["events"][0]["visual_beat"]
    sel = select_majors(
        {
            "characters": [{"id": "ent_0001", "name": "林砚之", "aliases": []}],
            "locations": [{"id": "loc_1", "name": "青川渡", "aliases": []}],
            "factions": [],
            "props": [],
        },
        [
            {
                "characters": [{"name": "林砚之"}],
                "locations": [{"name": "青川渡"}],
                "events": [{"summary": "林砚之抵达青川渡"}],
            }
        ],
    )
    assert "ent_0001" in sel["majors"]["characters"]
