from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.models import Job, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.runner import run_job
from fastapi.testclient import TestClient


def test_run_job_respects_cancel(db_session, settings: Settings):
    db_session.add(Project(id="p1", name="cancel-test"))
    db_session.add(Job(id="j1", project_id="p1", status="queued"))
    db_session.commit()
    paths = ProjectPaths(settings.data_root, "p1")
    paths.ensure()
    paths.source_txt.write_text(
        "第一章 开端\n\n李青云入山。\n\n第二章 风云\n\n青云拔剑。\n",
        encoding="utf-8",
    )
    llm = FakeLlm(
        default={
            "characters": [],
            "locations": [],
            "factions": [],
            "props": [],
            "events": [],
            "foreshadowing": [],
            "visual_cues": [],
            "voice_cues": [],
            "adaptation_notes": [],
        }
    )
    run_job(
        db_session,
        settings,
        job_id="j1",
        llm=llm,
        should_cancel=lambda: True,
    )
    job = db_session.get(Job, "j1")
    assert job is not None
    assert job.status == "cancelled"
    assert job.error_message == "cancelled_by_user"


def test_cancel_orphaned_running_job_finalizes_immediately(tmp_path):
    """Backend restart leaves DB status=running but no in-memory worker."""
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'a.db'}"))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "测取消"}).json()["id"]

    session = app.state.SessionLocal()
    try:
        session.add(Job(id="jorphan", project_id=pid, status="running", current_step="04_extract"))
        session.commit()
    finally:
        session.close()

    cancel = client.post(f"/api/projects/{pid}/jobs/jorphan/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


def test_start_job_clears_stale_active_without_worker(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'stale.db'}"))
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(
        default={
            "characters": [],
            "locations": [],
            "factions": [],
            "props": [],
            "events": [],
            "foreshadowing": [],
            "visual_cues": [],
            "voice_cues": [],
            "adaptation_notes": [],
        }
    )
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "stale"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.source_txt.write_text(
        "第一章 开端\n\n李青云入山。\n\n第二章 风云\n\n青云拔剑。\n",
        encoding="utf-8",
    )

    session = app.state.SessionLocal()
    try:
        session.add(
            Job(id="jstale", project_id=pid, status="running", current_step="04_extract")
        )
        session.commit()
    finally:
        session.close()

    # No register() → orphaned active job should be auto-cancelled, then new job starts
    started = client.post(f"/api/projects/{pid}/jobs", json={})
    assert started.status_code == 201
    assert started.json()["id"] != "jstale"

    stale = client.get(f"/api/projects/{pid}/jobs/jstale")
    assert stale.json()["status"] == "cancelled"


def test_cancel_live_job_then_force(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'a.db'}"))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "测取消2"}).json()["id"]

    session = app.state.SessionLocal()
    try:
        session.add(Job(id="jlive", project_id=pid, status="running", current_step="04_extract"))
        session.commit()
    finally:
        session.close()

    app.state.job_control.register("jlive")
    first = client.post(f"/api/projects/{pid}/jobs/jlive/cancel")
    assert first.status_code == 200
    assert first.json()["status"] == "cancelling"
    assert app.state.job_control.is_cancelled("jlive")

    second = client.post(f"/api/projects/{pid}/jobs/jlive/cancel")
    assert second.status_code == 200
    assert second.json()["status"] == "cancelled"

    latest = client.get(f"/api/projects/{pid}/jobs/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == "jlive"
    assert latest.json()["status"] == "cancelled"
