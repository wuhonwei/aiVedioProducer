import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.pipeline.shot_upgrade import (
    build_asset_plan,
    save_asset_plan,
    upgrade_shot_document,
    upgrade_shot_to_v2,
    write_shot_yamls,
)

router = APIRouter(tags=["shots"])


class ShotReviewBody(BaseModel):
    status: str = Field(description="needs_review|approved|rejected|needs_regen")
    note: str = ""


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _load_doc(paths: ProjectPaths) -> dict[str, Any]:
    if not paths.shot_script_json.exists():
        raise HTTPException(status_code=404, detail="Shot script not available yet")
    doc = json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
    return upgrade_shot_document(doc)


def _save_doc(paths: ProjectPaths, doc: dict[str, Any]) -> dict[str, Any]:
    doc = upgrade_shot_document(doc)
    paths.shot_script_dir.mkdir(parents=True, exist_ok=True)
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return doc


@router.get("/projects/{project_id}/shots")
def get_shots(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    return _load_doc(paths)


@router.get("/projects/{project_id}/shots/{shot_id}")
def get_shot(
    project_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    for shot in doc.get("shots") or []:
        if shot.get("shot_id") == shot_id:
            return shot
    raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")


@router.patch("/projects/{project_id}/shots/{shot_id}")
def patch_shot(
    project_id: str,
    shot_id: str,
    patch: dict[str, Any],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    found = None
    for i, shot in enumerate(doc.get("shots") or []):
        if shot.get("shot_id") == shot_id:
            updated = {**shot, **patch, "shot_id": shot_id}
            doc["shots"][i] = upgrade_shot_to_v2(updated, shot.get("global_order") or i + 1)
            found = doc["shots"][i]
            break
    if found is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    _save_doc(paths, doc)
    return found


@router.post("/projects/{project_id}/shots/{shot_id}/review")
def review_shot(
    project_id: str,
    shot_id: str,
    body: ShotReviewBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    found = None
    for i, shot in enumerate(doc.get("shots") or []):
        if shot.get("shot_id") == shot_id:
            review = dict(shot.get("review") or {})
            review["status"] = body.status
            if body.note:
                notes = list(review.get("notes") or [])
                notes.append(body.note)
                review["notes"] = notes
            shot["review"] = review
            doc["shots"][i] = upgrade_shot_to_v2(shot, shot.get("global_order") or i + 1)
            found = doc["shots"][i]
            break
    if found is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    _save_doc(paths, doc)
    return found


@router.post("/projects/{project_id}/shots/export-yaml")
def export_yaml(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    try:
        written = write_shot_yamls(paths.shots_dir, doc.get("shots") or [])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _save_doc(paths, doc)
    return {"count": len(written), "root": str(paths.shots_dir)}


@router.get("/projects/{project_id}/assets/plan")
def get_asset_plan(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    if paths.asset_plan_json.exists():
        return json.loads(paths.asset_plan_json.read_text(encoding="utf-8"))
    if not paths.shot_script_json.exists():
        raise HTTPException(status_code=404, detail="Asset plan not available yet")
    doc = _load_doc(paths)
    plan = build_asset_plan(doc.get("shots") or [])
    save_asset_plan(paths.asset_plan_json, plan)
    return plan


@router.post("/projects/{project_id}/assets/plan/regenerate")
def regenerate_asset_plan(
    project_id: str,
    approved_only: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    plan = build_asset_plan(doc.get("shots") or [], approved_only=approved_only)
    save_asset_plan(paths.asset_plan_json, plan)
    return plan
