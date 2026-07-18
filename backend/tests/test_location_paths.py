from pathlib import Path

from aivp.visual.paths import VisualPaths


def test_location_dirs(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    v.ensure_location("loc_0001")
    assert v.location_dir("loc_0001").exists()
    assert v.location_candidates_dir("loc_0001").exists()
    assert (v.root / "locations" / "loc_0001").exists()
    assert v.location_profile_json("loc_0001").parent.exists()
