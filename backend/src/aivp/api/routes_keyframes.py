from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.keyframes.generate import generate_keyframes
from aivp.keyframes.paths import KeyframePaths, safe_filename, safe_shot_id
from aivp.keyframes.store import (
    delete_candidate,
    derive_status,
    list_candidates,
    read_generation,
    read_selected,
    reject_keyframe,
    select_keyframe,
)
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.visual.image_backend import get_image_backend
from aivp.visual.paths import VisualPaths

router = APIRouter(tags=["keyframes"])


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _file_url(project_id: str, shot_id: str, filename: str) -> str:
    return f"/api/projects/{project_id}/keyframes/{shot_id}/files/{filename}"


def _patch_shot_keyframe_selection(
    paths: ProjectPaths, shot_id: str, filename: str
) -> None:
    if not paths.shot_script_json.exists():
        return
    try:
        doc = json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for shot in doc.get("shots") or []:
        if not isinstance(shot, dict) or shot.get("shot_id") != shot_id:
            continue
        gen = shot.get("generation") if isinstance(shot.get("generation"), dict) else {}
        gen["keyframe_status"] = "selected"
        gen["keyframe_file"] = filename
        shot["generation"] = gen
        try:
            paths.shot_script_json.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        return


class GenerateBody(BaseModel):
    count: int = 4
    use_location_lora: bool = False
    force: bool = False
    prompt_override: str = ""
    negative_override: str = ""
    character_lora_strength: float | None = None


class SelectBody(BaseModel):
    filename: str
    note: str = ""


class RejectBody(BaseModel):
    filename: str
    reason: str = ""


@router.post("/projects/{project_id}/keyframes/{shot_id}/generate")
def generate_keyframes_endpoint(
    project_id: str,
    shot_id: str,
    body: GenerateBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    body = body or GenerateBody()
    paths = ProjectPaths(settings.data_root, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    kpaths = KeyframePaths(settings.data_root, project_id)
    backend = get_image_backend(settings)
    try:
        out = generate_keyframes(
            paths,
            vpaths,
            kpaths,
            backend,
            shot_id,
            count=body.count,
            use_location_lora=body.use_location_lora,
            force=body.force,
            prompt_override=body.prompt_override,
            negative_override=body.negative_override,
            character_lora_strength=body.character_lora_strength,
            settings=settings,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    for cand in out.get("candidates") or []:
        fname = cand.get("file")
        if fname:
            cand["url"] = _file_url(project_id, shot_id, fname)
    return out


@router.get("/projects/{project_id}/keyframes/{shot_id}")
def get_keyframes(
    project_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    try:
        safe_shot_id(shot_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    kpaths = KeyframePaths(settings.data_root, project_id)
    candidates = list_candidates(kpaths, shot_id)
    for cand in candidates:
        fname = cand.get("file")
        if fname:
            cand["url"] = _file_url(project_id, shot_id, fname)
    selected = read_selected(kpaths, shot_id)
    if selected and selected.get("selected_file"):
        selected = dict(selected)
        selected["url"] = _file_url(project_id, shot_id, selected["selected_file"])
    return {
        "shot_id": shot_id,
        "status": derive_status(kpaths, shot_id),
        "candidates": candidates,
        "selected": selected,
        "generation": read_generation(kpaths, shot_id),
    }


@router.post("/projects/{project_id}/keyframes/{shot_id}/select")
def select_keyframe_endpoint(
    project_id: str,
    shot_id: str,
    body: SelectBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    kpaths = KeyframePaths(settings.data_root, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    try:
        result = select_keyframe(kpaths, shot_id, body.filename, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _patch_shot_keyframe_selection(paths, shot_id, result["selected_file"])
    return result


@router.post("/projects/{project_id}/keyframes/{shot_id}/reject")
def reject_keyframe_endpoint(
    project_id: str,
    shot_id: str,
    body: RejectBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    kpaths = KeyframePaths(settings.data_root, project_id)
    try:
        return reject_keyframe(
            kpaths, shot_id, body.filename, reason=body.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/projects/{project_id}/keyframes/{shot_id}/candidates/{filename}")
def delete_keyframe_candidate(
    project_id: str,
    shot_id: str,
    filename: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    kpaths = KeyframePaths(settings.data_root, project_id)
    try:
        return delete_candidate(kpaths, shot_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/projects/{project_id}/keyframes/{shot_id}/files/{filename}")
def get_keyframe_file(
    project_id: str,
    shot_id: str,
    filename: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_project(db, project_id)
    try:
        sid = safe_shot_id(shot_id)
        name = safe_filename(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    kpaths = KeyframePaths(settings.data_root, project_id)
    path = kpaths.candidates_dir(sid) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)
