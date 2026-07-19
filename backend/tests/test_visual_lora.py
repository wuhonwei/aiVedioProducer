import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.visual.candidates import generate_candidates
from aivp.visual.curate import curate_candidates
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.lora_train import export_train_package, prepare_train_package
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import build_lora_refs, ensure_profile, slug_trigger
from aivp.visual.sheets import generate_character_sheets
from aivp.visual.t2i import approve_lora, reject_lora
from aivp.visual.trainset_check import check_trainset


def test_slug_trigger_stable():
    assert slug_trigger("Lin Yan").endswith("_aivp")
    assert slug_trigger("林砚之").endswith("_aivp")


def _major_character() -> dict:
    return {
        "id": "ent_0001",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰长衫少年",
        "consistency_anchors": ["青灰长衫"],
        "wardrobe": {"default": "青灰长衫"},
    }


def test_generate_curate_and_train_package(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = _major_character()
    bible = {"characters": [character]}
    backend = StubImageBackend()
    out = generate_candidates(vpaths, bible, backend, count=4)
    assert out["count"] == 1
    assert len(out["characters"][0]["files"]) == 4
    again = generate_candidates(vpaths, bible, backend, count=2)
    assert len(again["characters"][0]["files"]) == 2
    all_cand = list(vpaths.candidates_dir("ent_0001").glob("*.png"))
    assert len(all_cand) == 6
    keep = out["characters"][0]["files"][:2]
    sheets = generate_character_sheets(vpaths, character, backend)
    sheet_files = [f["file"] for f in sheets["files"][:3]]
    assert (vpaths.sheets_dir("ent_0001") / sheet_files[0]).with_suffix(".txt").exists()
    curated = curate_candidates(
        vpaths, "ent_0001", keep, keep_sheets=sheet_files
    )
    assert curated["count"] == 2 + 3
    assert any(s["folder"] == "sheets" for s in curated["sources"])
    profile = ensure_profile(vpaths, character)
    assert profile["train_status"] == "curated_ready"
    package = prepare_train_package(vpaths, "ent_0001", profile)
    assert package["schema_version"] == 2
    assert package["trigger"]
    assert Path(package["output_dir"]).exists()
    assert len(package["images"]) == 5
    assert all(isinstance(img, dict) and "file" in img for img in package["images"])
    assert any(
        "turnaround" in img["file"] or "expr_" in img["file"] for img in package["images"]
    )
    assert all(package["trigger"] in img["caption"] for img in package["images"])
    assert "training" in package and "quality_check" in package


def test_trainset_check_and_package_gate(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p2")
    vpaths.ensure()
    character = _major_character()
    bible = {"characters": [character]}
    backend = StubImageBackend()
    cand = generate_candidates(vpaths, bible, backend, count=4)
    sheets = generate_character_sheets(vpaths, character, backend)
    sheet_names = [f["file"] for f in sheets["files"]]
    curate_candidates(
        vpaths,
        "ent_0001",
        cand["characters"][0]["files"],
        keep_sheets=sheet_names,
    )
    profile = ensure_profile(vpaths, character)
    check = check_trainset(vpaths, "ent_0001")
    assert check["image_count"] >= 8
    assert check["has_front"]
    assert check["can_train"] is True
    assert not check["missing_captions"]
    assert not check["trigger_mismatch"]

    packaged = export_train_package(vpaths, "ent_0001", require_can_train=True)
    assert packaged["packaged"] is True
    profile2 = json.loads(vpaths.profile_json("ent_0001").read_text(encoding="utf-8"))
    assert profile2["train_status"] == "package_ready"
    assert profile2["lora_ready"] is False


def test_probe_approve_sets_lora_ready(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p3")
    vpaths.ensure()
    character = _major_character()
    profile = ensure_profile(vpaths, character)
    profile["train_status"] = "trained"
    profile["probe_status"] = "pending"
    profile["lora_ready"] = False
    profile["lora_file"] = "linyan_aivp.safetensors"
    vpaths.lora_dir("ent_0001").mkdir(parents=True, exist_ok=True)
    (vpaths.lora_dir("ent_0001") / "linyan_aivp.safetensors").write_bytes(b"fake")
    from aivp.visual.profiles import save_profile

    save_profile(vpaths, profile)

    assert build_lora_refs(vpaths, ["ent_0001"], only_ready=True)[0] == []
    approved = approve_lora(vpaths, "ent_0001")
    assert approved["lora_ready"] is True
    refs, warnings = build_lora_refs(vpaths, ["ent_0001"], only_ready=True)
    assert len(refs) == 1
    assert not warnings
    assert refs[0]["trigger"].endswith("_aivp")
    assert refs[0]["file"] == "linyan_aivp.safetensors"

    rejected = reject_lora(vpaths, "ent_0001", note="style drift")
    assert rejected["lora_ready"] is False
    assert rejected["probe_status"] == "rejected"
    refs2, warnings2 = build_lora_refs(vpaths, ["ent_0001"], only_ready=True)
    assert refs2 == []
    assert any("lora_not_ready" in w for w in warnings2)


def test_visual_api_candidates(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'v.db'}", image_backend="stub")
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "视觉"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "id": "ent_0001",
                        "name": "林砚之",
                        "tier": "major",
                        "prompt_zh": "青灰长衫",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    listed = client.get(f"/api/projects/{pid}/visual/characters")
    assert listed.status_code == 200
    char0 = listed.json()["characters"][0]
    assert char0["trigger"].endswith("_aivp")
    assert char0["train_status"] == "not_started"
    assert char0["lora_ready"] is False

    job = client.post(f"/api/projects/{pid}/visual/candidates", json={"count": 3})
    assert job.status_code == 202
    job_id = job.json()["id"]
    status = client.get(f"/api/projects/{pid}/visual/jobs/{job_id}").json()
    assert status["status"] == "succeeded"
    files = status["result"]["characters"][0]["files"]
    assert len(files) == 3
    cur = client.post(
        f"/api/projects/{pid}/visual/characters/ent_0001/curate",
        json={"keep": files[:2]},
    )
    assert cur.status_code == 200
    check = client.get(f"/api/projects/{pid}/visual/characters/ent_0001/trainset/check")
    assert check.status_code == 200
    assert check.json()["can_train"] is False

    # Legacy sync train still exports package without requiring can_train.
    train = client.post(f"/api/projects/{pid}/visual/lora/train", json={})
    assert train.status_code == 200
    images = train.json()["results"][0]["dataset"]["images"]
    assert images
    assert isinstance(images[0], dict)

    # New package endpoint requires can_train.
    bad_pkg = client.post(f"/api/projects/{pid}/visual/characters/ent_0001/lora/package")
    assert bad_pkg.status_code == 400


def test_batch_lora_train_job_progress(tmp_path: Path):
    """Batch train runs sequentially and reports per-character items."""
    trainer = tmp_path / "fake_train.py"
    trainer.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'fake.safetensors').write_bytes(b'lora')\n",
        encoding="utf-8",
    )
    cmd = f'{sys.executable} "{trainer}" "{{output_dir}}"'
    app = create_app(
        Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{tmp_path / 'batch.db'}",
            image_backend="stub",
            lora_train_cmd=cmd,
        )
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "batch-train"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    chars = [
        {"id": "ent_0001", "name": "Lin", "tier": "major", "prompt_zh": "blue robe"},
        {"id": "ent_0002", "name": "Chen", "tier": "major", "prompt_zh": "brown robe"},
    ]
    paths.auto_bible_json.write_text(
        json.dumps({"characters": chars}, ensure_ascii=False), encoding="utf-8"
    )
    vpaths = VisualPaths(tmp_path, pid)
    backend = StubImageBackend()
    for ch in chars:
        ensure_profile(vpaths, ch)
        cand = generate_candidates(vpaths, {"characters": [ch]}, backend, count=4)
        sheets = generate_character_sheets(vpaths, ch, backend)
        sheet_names = [f["file"] for f in sheets["files"]]
        curate_candidates(
            vpaths,
            ch["id"],
            cand["characters"][0]["files"],
            keep_sheets=sheet_names,
        )
        export_train_package(vpaths, ch["id"], require_can_train=True)

    listed = client.get(f"/api/projects/{pid}/visual/characters").json()
    assert listed.get("lora_train_configured") is True

    job = client.post(
        f"/api/projects/{pid}/visual/lora/train/batch", json={"auto_package": False}
    )
    assert job.status_code == 202, job.text
    body = job.json()
    assert body["kind"] == "lora_train_batch"
    assert body["progress_total"] == 2

    status = client.get(f"/api/projects/{pid}/visual/jobs/{body['id']}").json()
    assert status["status"] == "succeeded", status
    assert status["progress_done"] == 2
    assert len(status["items"]) == 2
    assert all(it["status"] == "succeeded" for it in status["items"])
    assert all(it.get("lora_file") for it in status["items"])


def test_batch_lora_train_skips_already_trained(tmp_path: Path):
    """Already-trained characters with LoRA weights must not be re-queued."""
    trainer = tmp_path / "fake_train.py"
    trainer.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'fake.safetensors').write_bytes(b'lora')\n",
        encoding="utf-8",
    )
    cmd = f'{sys.executable} "{trainer}" "{{output_dir}}"'
    app = create_app(
        Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{tmp_path / 'batch_skip.db'}",
            image_backend="stub",
            lora_train_cmd=cmd,
        )
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "batch-skip"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    chars = [
        {"id": "ent_0001", "name": "Lin", "tier": "major", "prompt_zh": "blue robe"},
        {"id": "ent_0002", "name": "Chen", "tier": "major", "prompt_zh": "brown robe"},
    ]
    paths.auto_bible_json.write_text(
        json.dumps({"characters": chars}, ensure_ascii=False), encoding="utf-8"
    )
    vpaths = VisualPaths(tmp_path, pid)
    backend = StubImageBackend()
    for ch in chars:
        ensure_profile(vpaths, ch)
        cand = generate_candidates(vpaths, {"characters": [ch]}, backend, count=4)
        sheets = generate_character_sheets(vpaths, ch, backend)
        sheet_names = [f["file"] for f in sheets["files"]]
        curate_candidates(
            vpaths,
            ch["id"],
            cand["characters"][0]["files"],
            keep_sheets=sheet_names,
        )
        export_train_package(vpaths, ch["id"], require_can_train=True)

    # Mark Lin as already trained with weights on disk.
    lin_profile = json.loads(vpaths.profile_json("ent_0001").read_text(encoding="utf-8"))
    lin_lora = vpaths.lora_dir("ent_0001") / "c6797781a4e4b_aivp.safetensors"
    lin_lora.write_bytes(b"existing")
    lin_profile["train_status"] = "trained"
    lin_profile["status"] = "trained"
    lin_profile["lora_file"] = lin_lora.name
    lin_profile["lora_ready"] = False
    vpaths.profile_json("ent_0001").write_text(
        json.dumps(lin_profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    job = client.post(
        f"/api/projects/{pid}/visual/lora/train/batch", json={"auto_package": False}
    )
    assert job.status_code == 202, job.text
    body = job.json()
    assert body["progress_total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["character_id"] == "ent_0002"
    skipped = body.get("skipped") or []
    assert any(
        s.get("character_id") == "ent_0001" and s.get("error") == "already_trained"
        for s in skipped
    )

    status = client.get(f"/api/projects/{pid}/visual/jobs/{body['id']}").json()
    assert status["status"] == "succeeded", status
    assert status["progress_done"] == 1
    assert len(status["items"]) == 1
    assert status["items"][0]["character_id"] == "ent_0002"
    # Existing Lin weights must not be overwritten by the fake trainer.
    assert lin_lora.read_bytes() == b"existing"
