from collections import Counter

from aivp.visual.location_bootstrap_tuning import (
    load_location_bootstrap_tuning,
    merge_tuning,
    patches_from_failure_tags,
    save_location_bootstrap_tuning,
)
from aivp.visual.paths import VisualPaths


def test_has_people_patch():
    patches = patches_from_failure_tags(Counter({"has_people": 5, "other": 1}))
    assert patches.get("full_empty_boost") is True
    assert "person" in (patches.get("extra_negative") or "")


def test_merge_and_save(tmp_path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    v.ensure_location("loc_1")
    merged = merge_tuning({}, patches_from_failure_tags(["has_people", "has_people"]))
    save_location_bootstrap_tuning(v, "loc_1", merged)
    loaded = load_location_bootstrap_tuning(v, "loc_1")
    assert loaded.get("full_empty_boost") is True
