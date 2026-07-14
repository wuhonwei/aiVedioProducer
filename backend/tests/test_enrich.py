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
