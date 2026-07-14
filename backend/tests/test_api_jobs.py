from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm

SAMPLE = "\u7b2c\u4e00\u7ae0 \u5f00\u7aef\n\n\u674e\u9752\u4e91\u8d70\u8fdb\u9752\u4e91\u5c71\u3002\n\n\u7b2c\u4e8c\u7ae0 \u98ce\u4e91\n\n\u9752\u4e91\u62d4\u5251\u3002\n"

FAKE_EXTRACT = {
    "characters": [{"name": "\u674e\u9752\u4e91", "aliases": ["\u9752\u4e91"]}],
    "locations": [{"name": "\u9752\u4e91\u5c71", "aliases": []}],
    "factions": [],
    "props": [],
    "events": [{"summary": "\u5165\u5c71"}],
    "foreshadowing": [],
    "visual_cues": ["\u8fdc\u5c71"],
    "voice_cues": [],
    "adaptation_notes": [],
}


def test_create_project_upload_start_job_poll_succeeded(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}"))
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default=FAKE_EXTRACT)
    client = TestClient(app)

    pid = client.post("/api/projects", json={"name": "\u6d4b\u4e66"}).json()["id"]
    up = client.post(
        f"/api/projects/{pid}/source",
        files={"file": ("book.txt", SAMPLE.encode("utf-8"), "text/plain")},
    )
    assert up.status_code == 200

    jr = client.post(f"/api/projects/{pid}/jobs", json={})
    assert jr.status_code == 201
    job_id = jr.json()["id"]
    assert jr.json()["status"] in ("queued", "running", "succeeded")

    status = None
    for _ in range(50):
        status = client.get(f"/api/projects/{pid}/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "step_failed", "failed"):
            break
    assert status is not None
    assert status["status"] == "succeeded"


def test_health_ollama_endpoint(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}"))
    client = TestClient(app)
    r = client.get("/api/health/ollama")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert isinstance(body["ok"], bool)


def test_force_enrich_defaults_resume_step(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'b.db'}"))
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default=FAKE_EXTRACT)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "enrich"}).json()["id"]
    client.post(
        f"/api/projects/{pid}/source",
        files={"file": ("book.txt", SAMPLE.encode("utf-8"), "text/plain")},
    )
    # First full run
    first = client.post(f"/api/projects/{pid}/jobs", json={})
    assert first.status_code == 201
    # Force enrich-only relaunch
    second = client.post(
        f"/api/projects/{pid}/jobs",
        json={"force_enrich": True},
    )
    assert second.status_code == 201
    body = second.json()
    assert body["force_enrich"] is True
    assert body["resume_from_step"] == "06_enrich_assets"
