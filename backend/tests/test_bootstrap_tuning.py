from collections import Counter
from pathlib import Path

from aivp.visual.bootstrap_tuning import (
    apply_failure_tags,
    merge_tuning,
    patches_from_failure_tags,
)
from aivp.visual.paths import VisualPaths


def test_patches_from_half_body_tags():
    p = patches_from_failure_tags(Counter({"half_body": 5, "ok": 1}))
    assert p.get("full_body_boost") is True
    assert float(p.get("candidate_cfg") or 0) >= 11.0


def test_merge_and_persist(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    cid = "ent_0001"
    vpaths.ensure_character(cid)
    first = apply_failure_tags(vpaths, cid, ["half_body", "half_body", "busy_background"])
    assert first.get("full_body_boost") is True
    second = apply_failure_tags(vpaths, cid, ["shirtless_or_revealing"])
    assert second.get("outfit_lock_boost") is True
    assert second.get("full_body_boost") is True  # retained


def test_merge_extra_negative_dedupes():
    merged = merge_tuning(
        {"extra_negative": "half body, waist up"},
        {"extra_negative": "half body, bust shot"},
    )
    neg = merged["extra_negative"]
    assert neg.count("half body") == 1
    assert "bust shot" in neg
