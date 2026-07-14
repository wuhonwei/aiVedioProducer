import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _project_out(p: Project) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "export_version": p.export_version,
    }


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pid = _short_id()
    project = Project(id=pid, name=body.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    ProjectPaths(settings.data_root, pid).ensure()
    return _project_out(project)


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [_project_out(p) for p in rows]


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return _project_out(project)


@router.post("/projects/{project_id}/source")
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    paths = ProjectPaths(settings.data_root, project_id)
    paths.ensure()
    data = await file.read()
    paths.source_txt.write_bytes(data)
    return {"ok": True, "path": str(paths.source_txt), "bytes": len(data)}
