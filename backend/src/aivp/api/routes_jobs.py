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

ACTIVE_STATUSES = ("queued", "running", "cancelling")
TERMINAL_STATUSES = ("succeeded", "step_failed", "failed", "cancelled")


class JobCreate(BaseModel):
    resume_from_step: str | None = None
    force_enrich: bool = False
    force_shots: bool = False
    volume_id: str | None = None
    chapter_from: str | None = None
    chapter_to: str | None = None


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _job_flags(app) -> dict[str, dict[str, Any]]:
    flags = getattr(app.state, "job_flags", None)
    if flags is None:
        flags = {}
        app.state.job_flags = flags
    return flags


def _job_out(
    job: Job,
    *,
    force_enrich: bool | None = None,
    force_shots: bool | None = None,
    volume_id: str | None = None,
    chapter_from: str | None = None,
    chapter_to: str | None = None,
) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "current_step": job.current_step,
        "chunks_total": job.chunks_total,
        "chunks_done": job.chunks_done,
        "volumes_total": getattr(job, "volumes_total", 0) or 0,
        "volumes_done": getattr(job, "volumes_done", 0) or 0,
        "error_message": job.error_message,
        "resume_from_step": job.resume_from_step,
        "force_enrich": bool(force_enrich),
        "force_shots": bool(force_shots),
        "volume_id": volume_id,
        "chapter_from": chapter_from,
        "chapter_to": chapter_to,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _run_job_in_session(app, job_id: str) -> None:
    SessionLocal = app.state.SessionLocal
    settings = app.state.settings
    llm = app.state.llm
    shot_llm = getattr(app.state, "shot_llm", None)
    control = app.state.job_control
    flags = _job_flags(app).pop(job_id, {})
    force_enrich = bool(flags.get("force_enrich"))
    force_shots = bool(flags.get("force_shots"))
    control.register(job_id)
    session = SessionLocal()
    try:
        run_job(
            session,
            settings,
            job_id=job_id,
            llm=llm,
            should_cancel=lambda: control.is_cancelled(job_id),
            force_enrich=force_enrich,
            force_shots=force_shots,
            shot_llm=shot_llm,
            volume_id=flags.get("volume_id"),
            chapter_from=flags.get("chapter_from"),
            chapter_to=flags.get("chapter_to"),
        )
    except Exception:
        # run_job persists step_failed; swallow so the worker thread stays quiet
        pass
    finally:
        control.clear(job_id)
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

    control = request.app.state.job_control
    active = (
        db.query(Job)
        .filter(Job.project_id == project_id, Job.status.in_(ACTIVE_STATUSES))
        .order_by(Job.created_at.desc())
        .first()
    )
    if active:
        # Stale DB rows after backend restart have no in-memory worker — clear them.
        if not control.has_worker(active.id):
            active.status = "cancelled"
            active.error_message = "cancelled_stale_no_worker"
            db.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"项目已有进行中的任务 {active.id}（状态 {active.status}）。"
                    "请先在页面点击「终止」或「强制终止」。"
                ),
            )

    body = body or JobCreate()
    resume = body.resume_from_step
    # Force enrich implies restarting from asset enrichment unless caller overrides.
    if body.force_enrich and not resume:
        resume = "06_enrich_assets"
    # Force shots alone resumes from shot stage.
    if body.force_shots and not resume and not body.force_enrich:
        resume = "10_shot_script"
    job = Job(
        id=_short_id(),
        project_id=project_id,
        status="queued",
        resume_from_step=resume,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    app = request.app
    _job_flags(app)[job.id] = {
        "force_enrich": bool(body.force_enrich),
        "force_shots": bool(body.force_shots),
        "volume_id": body.volume_id,
        "chapter_from": body.chapter_from,
        "chapter_to": body.chapter_to,
    }
    if getattr(app.state, "run_jobs_inline", False):
        _run_job_in_session(app, job.id)
        db.refresh(job)
    else:
        # non-daemon: closing the browser does not kill the job; only process exit /
        # explicit cancel can stop it. Keep uvicorn process alive while job runs.
        thread = threading.Thread(
            target=_run_job_in_session,
            args=(app, job.id),
            daemon=False,
            name=f"aivp-job-{job.id}",
        )
        thread.start()
        app.state._last_job_thread = thread

    return _job_out(
        job,
        force_enrich=body.force_enrich,
        force_shots=body.force_shots,
        volume_id=body.volume_id,
        chapter_from=body.chapter_from,
        chapter_to=body.chapter_to,
    )


@router.get("/projects/{project_id}/jobs/latest")
def latest_job(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    job = (
        db.query(Job)
        .filter(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="No jobs for project")
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


def _finalize_cancelled(job: Job, db: Session, control) -> dict[str, Any]:
    job.status = "cancelled"
    job.error_message = "cancelled_by_user"
    db.commit()
    db.refresh(job)
    control.clear(job.id)
    return _job_out(job)


@router.post("/projects/{project_id}/jobs/{job_id}/cancel")
def cancel_job(
    project_id: str,
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Job already finished with status {job.status}",
        )

    control = request.app.state.job_control
    has_worker = control.has_worker(job_id)
    control.request_cancel(job_id)

    # Force finalize when:
    # - queued (not yet executing meaningful work)
    # - already cancelling (second click = hard stop in DB)
    # - no live worker (e.g. backend restarted; memory flag lost)
    if job.status in ("queued", "cancelling") or not has_worker:
        return _finalize_cancelled(job, db, control)

    job.status = "cancelling"
    db.commit()
    db.refresh(job)
    return _job_out(job)
