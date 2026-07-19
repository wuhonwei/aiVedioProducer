from pathlib import Path
import json

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
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
from aivp.visual.location_profiles import ensure_location_profile, save_location_profile
from aivp.visual.profiles import ensure_profile, read_profile_json, save_profile


def _seed_project_shots(tmp_path: Path, project_id: str) -> None:
    paths = ProjectPaths(tmp_path, project_id)
    paths.ensure()
    v = VisualPaths(tmp_path, project_id)
    v.ensure()
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


def _mark_character_lora_ready(v: VisualPaths, character_id: str) -> None:
    v.ensure_character(character_id)
    profile = read_profile_json(v.profile_json(character_id)) or {"character_id": character_id}
    profile["lora_ready"] = True
    lora_dir = v.lora_dir(character_id)
    lora_dir.mkdir(parents=True, exist_ok=True)
    lora_file = lora_dir / "model.safetensors"
    lora_file.write_bytes(b"lora")
    profile["lora_file"] = lora_file.name
    save_profile(v, profile)


def _mark_location_lora_ready(v: VisualPaths, location_id: str) -> None:
    v.ensure_location(location_id)
    profile_path = v.location_profile_json(location_id)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["lora_ready"] = True
    lora_dir = v.location_lora_dir(location_id)
    lora_dir.mkdir(parents=True, exist_ok=True)
    lora_file = lora_dir / "model.safetensors"
    lora_file.write_bytes(b"lora")
    profile["lora_file"] = lora_file.name
    save_location_profile(v, profile)


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
    assert out["status"] == "succeeded"
    assert len(out["candidates"]) == 1
    assert len(list_candidates(k, "shot_000001")) == 1
    assert any("lora" in w.lower() or "not_ready" in w for w in out["warnings"])


def test_generate_keyframes_force_clears_existing(tmp_path: Path):
    paths, v, k = _seed_shot_project(tmp_path)
    generate_keyframes(paths, v, k, StubImageBackend(), "shot_000001", count=2)
    assert len(list_candidates(k, "shot_000001")) == 2
    select_keyframe(k, "shot_000001", "kf_0001.png")
    assert k.selected_json("shot_000001").exists()

    out = generate_keyframes(
        paths,
        v,
        k,
        StubImageBackend(),
        "shot_000001",
        count=1,
        force=True,
    )
    assert out["status"] == "succeeded"
    assert len(out["candidates"]) == 1
    files = {c["file"] for c in list_candidates(k, "shot_000001")}
    assert files == {"kf_0001.png"}
    assert not k.selected_json("shot_000001").exists()


def test_generate_keyframes_warns_too_many_loras(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    char_ids: list[str] = []
    for i in range(1, 5):
        cid = f"ent_{i}"
        char_ids.append(cid)
        ensure_profile(v, {"id": cid, "name": f"角色{i}", "prompt_zh": "测试"})
        _mark_character_lora_ready(v, cid)
    doc = {
        "schema_version": 2,
        "shots": [
            {
                "shot_id": "shot_000001",
                "visual_prompt": "群像镜头",
                "negative_prompt": "lowres",
                "asset_refs": {"characters": char_ids, "locations": [], "props": []},
                "generation": {},
            }
        ],
    }
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )

    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=1
    )
    assert out["status"] == "succeeded"
    assert "too_many_loras" in out["warnings"]


def test_generate_keyframes_warns_too_many_loras_with_location(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    loc_id = "loc_1"
    ensure_location_profile(v, {"id": loc_id, "name": "渡口", "prompt_zh": "古渡"})
    _mark_location_lora_ready(v, loc_id)
    char_ids: list[str] = []
    for i in range(1, 4):
        cid = f"ent_{i}"
        char_ids.append(cid)
        ensure_profile(v, {"id": cid, "name": f"角色{i}", "prompt_zh": "测试"})
        _mark_character_lora_ready(v, cid)
    doc = {
        "schema_version": 2,
        "shots": [
            {
                "shot_id": "shot_000001",
                "visual_prompt": "渡口群像",
                "negative_prompt": "lowres",
                "asset_refs": {
                    "characters": char_ids,
                    "locations": [loc_id],
                    "props": [],
                },
                "generation": {},
            }
        ],
    }
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )

    out = generate_keyframes(
        paths,
        v,
        k,
        StubImageBackend(),
        "shot_000001",
        count=1,
        use_location_lora=True,
    )
    assert out["status"] == "succeeded"
    assert "too_many_loras" in out["warnings"]


def test_generate_keyframes_resolves_cast_names_when_asset_refs_empty(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    paths.assets_json.parent.mkdir(parents=True, exist_ok=True)
    paths.assets_json.write_text(
        json.dumps(
            {
                "characters": [{"id": "ent_1", "name": "林", "canonical_name": "林"}],
                "locations": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ch = {"id": "ent_1", "name": "林", "tier": "major", "prompt_zh": "青衣少年"}
    ensure_profile(v, ch)
    _mark_character_lora_ready(v, "ent_1")
    doc = {
        "schema_version": 2,
        "shots": [
            {
                "shot_id": "shot_000001",
                "visual_prompt": "立于渡口远眺",
                "negative_prompt": "lowres",
                "cast": ["林"],
                "asset_refs": {"characters": [], "locations": [], "props": []},
                "generation": {},
            }
        ],
    }
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )

    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=1
    )
    assert out["status"] == "succeeded"
    assert out["generation"]["character_ids"] == ["ent_1"]
    gen = read_generation(k, "shot_000001")
    assert gen and gen["character_ids"] == ["ent_1"]
    assert "character_lora_not_ready:ent_1" not in out["warnings"]


def test_keyframes_api_generate_get_select(tmp_path: Path):
    app = create_app(
        Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{tmp_path / 'kf.db'}",
            image_backend="stub",
        )
    )
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "kf"}).json()["id"]
    _seed_project_shots(tmp_path, pid)
    r = client.post(
        f"/api/projects/{pid}/keyframes/shot_000001/generate",
        json={"count": 2, "use_location_lora": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["candidates"]) == 2
    g = client.get(f"/api/projects/{pid}/keyframes/shot_000001")
    assert g.status_code == 200
    assert g.json()["status"] in {"candidates", "empty"}
    fname = body["candidates"][0]["file"]
    s = client.post(
        f"/api/projects/{pid}/keyframes/shot_000001/select",
        json={"filename": fname, "note": "ok"},
    )
    assert s.status_code == 200
    assert s.json()["selected_file"] == fname
    file_r = client.get(
        f"/api/projects/{pid}/keyframes/shot_000001/files/{fname}"
    )
    assert file_r.status_code == 200
