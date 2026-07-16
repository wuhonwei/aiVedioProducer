import json
from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.visual.candidates import generate_candidates
from aivp.visual.curate import curate_candidates
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.lora_train import prepare_train_package
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, slug_trigger
from aivp.visual.sheets import generate_character_sheets


def test_slug_trigger_stable():
    assert slug_trigger("Lin Yan").endswith("_aivp")
    assert slug_trigger("林砚之").endswith("_aivp")


def test_generate_curate_and_train_package(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰长衫少年",
        "consistency_anchors": ["青灰长衫"],
        "wardrobe": {"default": "青灰长衫"},
    }
    bible = {"characters": [character]}
    backend = StubImageBackend()
    out = generate_candidates(vpaths, bible, backend, count=4)
    assert out["count"] == 1
    assert len(out["characters"][0]["files"]) == 4
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
    package = prepare_train_package(vpaths, "ent_0001", profile)
    assert package["trigger"]
    assert Path(package["output_dir"]).exists()
    assert len(package["images"]) == 5
    assert any("turnaround" in n or "expr_" in n for n in package["images"])


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
    assert listed.json()["characters"][0]["trigger"].endswith("_aivp")
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
    train = client.post(f"/api/projects/{pid}/visual/lora/train", json={})
    assert train.status_code == 200
    assert train.json()["results"][0]["dataset"]["images"]
