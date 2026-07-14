import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Job, Project
from aivp.pipeline.runner import run_job

router = APIRouter(tags=["jobs"])


class JobCreate(BaseModel):
    resume_from_step: str | None = None


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _job_out(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "current_step": job.current_step,
        "chunks_total": job.chunks_total,
        "chunks_done": job.chunks_done,
        "error_message": job.error_message,
        "resume_from_step": job.resume_from_step,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _run_job_in_session(app, job_id: str) -> None:
    SessionLocal = app.state.SessionLocal
    settings = app.state.settings
    llm = app.state.llm
    session = SessionLocal()
    try:
        run_job(session, settings, job_id=job_id, llm=llm)
    except Exception:
        # run_job already persisted step_failed; swallow so thread does not crash loudly
        pass
    finally:
        session.close()


@router.post("/projects/{project_id}/jobs", status_code=201)
def start_job(
    project_id: str,
    request: Request,
    body: JobCreate | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    body = body or JobCreate()
    job = Job(
        id=_short_id(),
        project_id=project_id,
        status="queued",
        resume_from_step=body.resume_from_step,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    app = request.app
    if getattr(app.state, "run_jobs_inline", False):
        _run_job_in_session(app, job.id)
        db.refresh(job)
    else:
        thread = threading.Thread(
            target=_run_job_in_session,
            args=(app, job.id),
            daemon=True,
        )
        thread.start()
        app.state._last_job_thread = thread

    return _job_out(job)


@router.get("/projects/{project_id}/jobs/{job_id}")
def get_job(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_out(job)
