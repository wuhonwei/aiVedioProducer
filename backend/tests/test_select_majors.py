from aivp.pipeline.select_majors import select_majors


def test_select_majors_ranks_by_mentions():
    entities = {
        "characters": [
            {"id": "ent_0001", "name": "林砚之", "aliases": []},
            {"id": "ent_0002", "name": "路人甲", "aliases": []},
        ],
        "locations": [{"id": "loc_1", "name": "青川渡", "aliases": []}],
        "factions": [],
        "props": [{"id": "p1", "name": "玉佩", "aliases": ["忠守"]}],
    }
    extracts = [
        {
            "characters": [{"name": "林砚之"}],
            "locations": [{"name": "青川渡"}],
            "events": [{"summary": "林砚之抵达青川渡寻找玉佩"}],
            "visual_cues": ["青川渡江雾"],
        },
        {
            "characters": [{"name": "林砚之"}],
            "events": [{"summary": "林砚之再访青川渡"}],
        },
    ]
    out = select_majors(
        entities,
        extracts,
        limits={"characters": 1, "locations": 1, "props": 1, "factions": 0},
    )
    assert out["majors"]["characters"] == ["ent_0001"]
    assert out["majors"]["locations"] == ["loc_1"]
    assert out["majors"]["props"] == ["p1"]
