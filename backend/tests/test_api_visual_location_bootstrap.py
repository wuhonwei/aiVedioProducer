from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths


def _seed(client: TestClient, tmp_path: Path) -> str:
    pid = client.post("/api/projects", json={"name": "loc-bootstrap"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        __import__("json").dumps(
            {
                "characters": [],
                "locations": [
                    {
                        "id": "loc_0001",
                        "name": "渡口",
                        "tier": "major",
                        "prompt_zh": "青石渡口晨雾",
                        "materials": ["青石"],
                        "palette": ["青灰"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths.entities_json.parent.mkdir(parents=True, exist_ok=True)
    paths.entities_json.write_text(
        __import__("json").dumps(
            {
                "locations": [
                    {
                        "id": "loc_0001",
                        "name": "渡口",
                        "evidence": "青石埠头，江雾弥漫",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pid


def test_location_bootstrap_job_confirm(tmp_path: Path):
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{tmp_path / 'loc.db'}",
        image_backend="stub",
        location_bootstrap_lock_count=10,
        location_bootstrap_lock_batch_retries=1,
        location_bootstrap_slot_retries=1,
        location_bootstrap_archive_top_k=2,
    )
    app = create_app(settings)
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = _seed(client, tmp_path)

    job = client.post(
        f"/api/projects/{pid}/visual/locations/bootstrap",
        json={"location_ids": ["loc_0001"]},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    assert job.json()["kind"] == "visual_location_bootstrap"
    body = client.get(f"/api/projects/{pid}/visual/jobs/{jid}").json()
    assert body["status"] == "succeeded", body.get("error")
    assert body["result"]["locations"][0]["status"] == "awaiting_confirm"

    listed = client.get(f"/api/projects/{pid}/visual/locations").json()
    loc = listed["locations"][0]
    assert loc["bootstrap_status"] == "awaiting_confirm"
    assert loc["look_lock_ready"] is True
    archive = loc.get("look_lock_archive") or []
    assert archive

    swap = client.post(
        f"/api/projects/{pid}/visual/locations/loc_0001/bootstrap/swap-look-lock",
        json={"filename": archive[0], "folder": "look_lock_archive"},
    )
    assert swap.status_code == 200, swap.text

    confirm = client.post(
        f"/api/projects/{pid}/visual/locations/loc_0001/bootstrap/confirm"
    )
    assert confirm.status_code == 200
    assert confirm.json()["bootstrap_status"] == "confirmed"
    assert confirm.json()["train_status"] == "curated_ready"
