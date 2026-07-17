from aivp.pipeline.asset_plan import build_asset_plan, patch_asset_plan_entry
from aivp.pipeline.shot_upgrade import (
    build_shot_script_index,
    upgrade_shot_to_v2,
    write_shot_yamls,
)


def test_upgrade_shot_to_v2_production_fields():
    shot = upgrade_shot_to_v2(
        {
            "shot_id": "sh_e1_01",
            "event_id": "event_0001",
            "chapter_id": "chapter_0001",
            "chunk_id": "chapter_0001_chunk_0001",
            "order": 1,
            "shot_type": "medium",
            "camera": "中景",
            "action": "推门",
            "cast": ["林澈"],
            "location_name": "破庙",
            "duration_sec": 4,
            "evidence": "血迹延到庙门",
        },
        1,
        name_to_id={"林澈": "char_0001", "破庙": "loc_0001"},
    )
    assert shot["episode_id"] == "EP001"
    assert shot["scene_id"]
    assert shot["review_status"] == "needs_review"
    assert shot["locked"] is False
    assert shot["generation_status"] == "not_started"
    assert shot["camera_movement"]
    assert shot["lens"]
    assert shot["composition"]
    assert shot["negative_prompt"] == ""
    assert shot["location_id"] == "loc_0001"
    assert "char_0001" in shot["asset_refs"]["characters"]
    assert shot["source_refs"][0]["event_id"] == "event_0001"
    assert shot["source_refs"][0]["evidence"]
    assert isinstance(shot["camera"], dict)
    assert shot["assets_required"]["characters"] == ["林澈"]


def test_asset_plan_approved_only_and_ids():
    shots = [
        upgrade_shot_to_v2(
            {
                "order": 1,
                "action": "a",
                "cast": ["林澈"],
                "location_name": "破庙",
                "props": ["短刀"],
                "chapter_id": "chapter_0001",
                "event_id": "e1",
                "visual_score": 0.9,
            },
            1,
            name_to_id={"林澈": "char_0001", "破庙": "loc_0001", "短刀": "prop_0001"},
        )
    ]
    empty = build_asset_plan(shots, approved_only=True)
    assert empty["generated_from"]["shot_count"] == 0
    assert empty["characters"] == []

    shots[0]["review"]["status"] = "approved"
    shots[0]["review_status"] = "approved"
    plan = build_asset_plan(
        shots,
        approved_only=True,
        entities={
            "characters": [{"id": "char_0001", "name": "林澈"}],
            "locations": [{"id": "loc_0001", "name": "破庙"}],
            "props": [{"id": "prop_0001", "name": "短刀"}],
        },
    )
    assert plan["schema_version"] == 1
    assert plan["characters"][0]["id"] == "char_0001"
    assert plan["characters"][0]["shot_ids"]
    assert plan["locations"][0]["needs_concept_art"] in (True, False)
    assert plan["props"][0]["needs_reference"] in (True, False)
    patched = patch_asset_plan_entry(plan, "characters", "char_0001", {"status": "approved"})
    assert patched["characters"][0]["status"] == "approved"


def test_yaml_and_index(tmp_path):
    shots = [
        upgrade_shot_to_v2(
            {
                "order": 1,
                "action": "a",
                "cast": ["林澈"],
                "location_name": "破庙",
                "chapter_id": "ch001",
                "event_id": "e1",
            },
            1,
        )
    ]
    shots[0]["review_status"] = "approved"
    shots[0]["review"]["status"] = "approved"
    written = write_shot_yamls(tmp_path / "shots", shots)
    assert written
    assert written[0].exists()
    only = write_shot_yamls(tmp_path / "shots2", shots, approved_only=True)
    assert len(only) == 1
    none = write_shot_yamls(
        tmp_path / "shots3",
        [{**shots[0], "review_status": "needs_review", "review": {"status": "needs_review"}, "locked": False}],
        approved_only=True,
    )
    assert none == []
    index = build_shot_script_index(
        {"shots": shots, "event_count": 1, "generated_at": "t", "volumes": []}
    )
    assert index["shot_count"] == 1
    assert index["events"]
    assert index["chapters"]
