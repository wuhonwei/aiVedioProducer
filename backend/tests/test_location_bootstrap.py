from pathlib import Path

from aivp.config import Settings
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.location_bootstrap import bootstrap_location
from aivp.visual.location_look_lock import location_look_lock_ref_path
from aivp.visual.location_profiles import read_location_profile
from aivp.visual.paths import VisualPaths


def test_bootstrap_location_awaiting_confirm(tmp_path: Path):
    settings = Settings(data_root=tmp_path, image_backend="stub")
    settings.location_bootstrap_lock_count = 10
    settings.location_bootstrap_lock_batch_retries = 1
    settings.location_bootstrap_slot_retries = 1
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {
        "id": "loc_1",
        "name": "渡口",
        "tier": "major",
        "prompt_zh": "青石渡口晨雾",
        "materials": ["青石"],
    }
    entity = {"id": "loc_1", "evidence": "青石埠头，江雾"}
    out = bootstrap_location(
        v,
        loc,
        StubImageBackend(),
        settings=settings,
        vision=None,
        entity=entity,
    )
    assert out["status"] == "awaiting_confirm"
    assert location_look_lock_ref_path(v, "loc_1")
    profile = read_location_profile(v.location_profile_json("loc_1"))
    assert profile is not None
    assert profile.get("bootstrap_status") == "awaiting_confirm"
    assert list(v.location_curated_dir("loc_1").glob("*.png"))
