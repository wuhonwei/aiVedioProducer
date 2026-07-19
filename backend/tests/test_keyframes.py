from pathlib import Path
import json

from aivp.keyframes.paths import KeyframePaths
from aivp.keyframes.store import (
    delete_candidate,
    derive_status,
    list_candidates,
    next_candidate_stem,
    reject_keyframe,
    select_keyframe,
)


def test_keyframe_paths_ensure(tmp_path: Path):
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    k.ensure_shot("shot_000001")
    assert k.candidates_dir("shot_000001").is_dir()
    assert k.generation_json("shot_000001").parent == k.shot_dir("shot_000001")


def test_select_reject_delete_cycle(tmp_path: Path):
    k = KeyframePaths(tmp_path, "p1")
    k.ensure_shot("shot_1")
    cand = k.candidates_dir("shot_1")
    (cand / "kf_0001.png").write_bytes(b"png")
    (cand / "kf_0001.json").write_text(
        json.dumps({"file": "kf_0001.png", "quality": {"status": "unchecked", "warnings": []}}),
        encoding="utf-8",
    )
    (cand / "kf_0002.png").write_bytes(b"png2")
    (cand / "kf_0002.json").write_text(
        json.dumps({"file": "kf_0002.png", "quality": {"status": "unchecked", "warnings": []}}),
        encoding="utf-8",
    )

    assert derive_status(k, "shot_1") == "candidates"
    assert next_candidate_stem(k, "shot_1") == "kf_0003"

    sel = select_keyframe(k, "shot_1", "kf_0002.png", note="best")
    assert sel["selected_file"] == "kf_0002.png"
    assert sel["review_status"] == "approved"
    assert derive_status(k, "shot_1") == "selected"

    rej = reject_keyframe(k, "shot_1", "kf_0002.png", reason="bad face")
    assert rej["cleared_selection"] is True
    assert derive_status(k, "shot_1") in {"rejected", "candidates"}

    delete_candidate(k, "shot_1", "kf_0001.png")
    files = {c["file"] for c in list_candidates(k, "shot_1")}
    assert "kf_0001.png" not in files
    assert "kf_0002.png" in files
