from pathlib import Path

from aivp.visual.location_profiles import (
    ensure_location_profile,
    location_trigger,
    read_location_profile,
)
from aivp.visual.paths import VisualPaths


def test_location_trigger_suffix():
    assert location_trigger("青渡川").endswith("_loc_aivp")
    assert location_trigger("QingDu").endswith("_loc_aivp")


def test_ensure_profile_from_bible_card(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {
        "id": "loc_1",
        "name": "渡口",
        "tier": "major",
        "prompt_zh": "晨雾渡口，青石埠头",
    }
    p = ensure_location_profile(v, loc)
    assert p["trigger"].endswith("_loc_aivp")
    assert p["prompt_zh"]
    assert p.get("location_id") == "loc_1"
    assert "character_id" not in p
    loaded = read_location_profile(v.location_profile_json("loc_1"))
    assert loaded is not None
    assert loaded["location_id"] == "loc_1"
