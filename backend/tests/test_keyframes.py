from pathlib import Path
import json

from aivp.keyframes.generate import generate_keyframes
from aivp.keyframes.paths import KeyframePaths
from aivp.keyframes.store import (
    delete_candidate,
    derive_status,
    list_candidates,
    next_candidate_stem,
    read_generation,
    reject_keyframe,
    select_keyframe,
)
from aivp.paths import ProjectPaths
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile


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


def _seed_shot_project(tmp_path: Path) -> tuple[ProjectPaths, VisualPaths, KeyframePaths]:
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    ch = {"id": "ent_1", "name": "林", "tier": "major", "prompt_zh": "青衣少年"}
    ensure_profile(v, ch)
    doc = {
        "schema_version": 2,
        "shots": [
            {
                "shot_id": "shot_000001",
                "visual_prompt": "立于渡口远眺",
                "negative_prompt": "lowres",
                "cast": ["林"],
                "asset_refs": {"characters": ["ent_1"], "locations": [], "props": []},
                "generation": {},
            }
        ],
    }
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    return paths, v, k


def test_generate_keyframes_writes_candidates(tmp_path: Path):
    paths, v, k = _seed_shot_project(tmp_path)
    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=2
    )
    assert out["status"] == "succeeded"
    assert len(out["candidates"]) == 2
    assert len(list_candidates(k, "shot_000001")) == 2
    gen = read_generation(k, "shot_000001")
    assert gen and gen["candidate_count"] == 2
    assert gen["use_location_lora"] is False


def test_generate_keyframes_warns_when_lora_missing(tmp_path: Path):
    paths, v, k = _seed_shot_project(tmp_path)
    # profile exists but lora_ready false / no file
    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=1
    )
    assert any("lora" in w.lower() or "not_ready" in w for w in out["warnings"])
