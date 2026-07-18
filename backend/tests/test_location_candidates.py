from pathlib import Path

from aivp.visual.image_backend import StubImageBackend
from aivp.visual.location_candidates import generate_location_candidates_for
from aivp.visual.location_profiles import ensure_location_profile
from aivp.visual.paths import VisualPaths


def test_generate_location_candidates_writes_pngs(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {
        "id": "loc_1",
        "name": "渡口",
        "tier": "major",
        "prompt_zh": "晨雾青石渡口",
    }
    ensure_location_profile(v, loc)
    out = generate_location_candidates_for(v, loc, StubImageBackend(), count=2)
    assert len(out["files"]) == 2
    txt = (
        v.location_candidates_dir("loc_1") / out["files"][0]
    ).with_suffix(".txt").read_text(encoding="utf-8")
    assert (
        "people" in txt.lower()
        or "empty" in txt.lower()
        or "无人" in txt
        or "no people" in txt.lower()
    )
