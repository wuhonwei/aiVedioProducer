from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.bible.overlay import merge_bible
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.visual.candidates import generate_candidates
from aivp.visual.curate import curate_candidates
from aivp.visual.image_backend import get_image_backend
from aivp.visual.lora_train import run_lora_train
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import character_status, ensure_profile, load_major_characters
from aivp.visual.sheets import generate_character_sheets
from aivp.visual.t2i import generate_with_character

_VISUAL_FOLDERS = frozenset({"candidates", "curated", "generations", "lora", "sheets"})

router = APIRouter(tags=["visual"])


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _load_bible(settings: Settings, project_id: str) -> dict:
    paths = ProjectPaths(settings.data_root, project_id)
    auto = {}
    overlay = {}
    if paths.auto_bible_json.exists():
        auto = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
    if paths.overlay_json.exists():
        overlay = json.loads(paths.overlay_json.read_text(encoding="utf-8"))
    if not auto and not overlay:
        raise HTTPException(status_code=404, detail="Story bible not available yet")
    return merge_bible(auto, overlay)


def _job_path(vpaths: VisualPaths, job_id: str) -> Path:
    return vpaths.jobs_dir / f"{job_id}.json"


def _write_job(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class CandidatesBody(BaseModel):
    character_ids: list[str] | None = None
    count: int = 8


class CurateBody(BaseModel):
    keep: list[str] = Field(default_factory=list)


class TrainBody(BaseModel):
    character_ids: list[str] | None = None


class T2IBody(BaseModel):
    character_id: str
    prompt: str
    shot_id: str | None = None


class SheetsBody(BaseModel):
    character_id: str


@router.get("/projects/{project_id}/visual/characters")
def list_visual_characters(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    items = []
    for ch in load_major_characters(bible):
        profile = ensure_profile(vpaths, ch)
        items.append(character_status(vpaths, profile["character_id"], profile))
    return {"characters": items, "backend": settings.image_backend}


@router.post("/projects/{project_id}/visual/candidates", status_code=202)
def start_candidates(
    project_id: str,
    request: Request,
    body: CandidatesBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    body = body or CandidatesBody()
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "visual_candidates",
        "status": "queued",
        "progress_done": 0,
        "progress_total": 0,
        "error": None,
        "result": None,
    }
    path = _job_path(vpaths, job_id)
    _write_job(path, job)

    def _worker() -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "running"
        _write_job(path, data)
        try:
            backend = get_image_backend(settings)

            def on_progress(done: int, total: int) -> None:
                data["progress_done"] = done
                data["progress_total"] = total
                _write_job(path, data)

            result = generate_candidates(
                vpaths,
                bible,
                backend,
                character_ids=body.character_ids,
                count=body.count,
                on_progress=on_progress,
            )
            data["status"] = "succeeded"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(target=_worker, daemon=False, name=f"aivp-visual-{job_id}").start()
    return job


@router.get("/projects/{project_id}/visual/jobs/{job_id}")
def get_visual_job(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    path = _job_path(VisualPaths(settings.data_root, project_id), job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="visual job not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/projects/{project_id}/visual/characters/{character_id}/curate")
def curate_character(
    project_id: str,
    character_id: str,
    body: CurateBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    return curate_candidates(vpaths, character_id, body.keep)


@router.post("/projects/{project_id}/visual/lora/train")
def train_lora(
    project_id: str,
    body: TrainBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    body = body or TrainBody()
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    majors = load_major_characters(bible)
    if body.character_ids:
        want = set(body.character_ids)
        majors = [c for c in majors if c.get("id") in want]
    results = []
    for ch in majors:
        cid = str(ch.get("id"))
        ensure_profile(vpaths, ch)
        results.append(run_lora_train(vpaths, cid, settings))
    return {"results": results}


@router.post("/projects/{project_id}/visual/t2i")
def t2i(
    project_id: str,
    body: T2IBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    backend = get_image_backend(settings)
    return generate_with_character(
        vpaths,
        body.character_id,
        body.prompt,
        backend,
        shot_id=body.shot_id,
    )


@router.post("/projects/{project_id}/visual/sheets", status_code=202)
def start_sheets(
    project_id: str,
    request: Request,
    body: SheetsBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    majors = load_major_characters(bible)
    character = next((c for c in majors if str(c.get("id")) == body.character_id), None)
    if not character:
        raise HTTPException(status_code=404, detail="character not found")
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "visual_sheets",
        "status": "queued",
        "progress_done": 0,
        "progress_total": 0,
        "error": None,
        "result": None,
    }
    path = _job_path(vpaths, job_id)
    _write_job(path, job)

    def _worker() -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "running"
        _write_job(path, data)
        try:
            backend = get_image_backend(settings)

            def on_progress(done: int, total: int) -> None:
                data["progress_done"] = done
                data["progress_total"] = total
                _write_job(path, data)

            result = generate_character_sheets(
                vpaths,
                character,
                backend,
                on_progress=on_progress,
            )
            data["status"] = "succeeded"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(target=_worker, daemon=False, name=f"aivp-sheets-{job_id}").start()
    return job


@router.get("/projects/{project_id}/visual/characters/{character_id}/files/{folder}/{filename}")
def get_visual_file(
    project_id: str,
    character_id: str,
    folder: str,
    filename: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_project(db, project_id)
    if folder not in _VISUAL_FOLDERS:
        raise HTTPException(status_code=400, detail="invalid folder")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    vpaths = VisualPaths(settings.data_root, project_id)
    path = vpaths.character_dir(character_id) / folder / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


@router.delete("/projects/{project_id}/visual/characters/{character_id}/files/{folder}/{filename}")
def delete_visual_file(
    project_id: str,
    character_id: str,
    folder: str,
    filename: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    if folder not in {"candidates", "generations", "sheets"}:
        raise HTTPException(status_code=400, detail="folder not deletable")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    vpaths = VisualPaths(settings.data_root, project_id)
    path = vpaths.character_dir(character_id) / folder / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    path.unlink()
    for side in (path.with_suffix(".json"), path.with_suffix(".txt"), path.with_suffix(".meta.json")):
        if side.exists():
            side.unlink()
    # Also drop sidecar named like file.png.meta.json handled above; cand captions use .txt
    return {"deleted": True, "folder": folder, "filename": filename}
