import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths

router = APIRouter(tags=["shots"])


@router.get("/projects/{project_id}/shots")
def get_shots(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    paths = ProjectPaths(settings.data_root, project_id)
    if not paths.shot_script_json.exists():
        raise HTTPException(status_code=404, detail="Shot script not available yet")
    return json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
