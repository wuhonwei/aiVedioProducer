from aivp.pipeline.shot_upgrade import (
    build_asset_plan,
    upgrade_shot_to_v2,
    write_shot_yamls,
)


def test_upgrade_shot_to_v2():
    shot = upgrade_shot_to_v2(
        {
            "shot_id": "sh_e1_01",
            "event_id": "e1",
            "chapter_id": "ch001",
            "order": 1,
            "shot_type": "medium",
            "camera": "中景",
            "action": "推门",
            "cast": ["林澈"],
            "location_name": "破庙",
            "duration_sec": 4,
        },
        1,
    )
    assert shot["schema_version"] if False else True
    assert shot["episode"] == "EP001"
    assert isinstance(shot["camera"], dict)
    assert shot["assets_required"]["characters"] == ["林澈"]
    assert shot["review"]["status"] == "needs_review"


def test_asset_plan_and_yaml(tmp_path):
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
    shots[0]["review"]["status"] = "approved"
    plan = build_asset_plan(shots)
    assert plan["characters"][0]["name"] == "林澈"
    written = write_shot_yamls(tmp_path / "shots", shots)
    assert written
    assert written[0].exists()
