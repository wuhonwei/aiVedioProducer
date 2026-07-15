import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths

router = APIRouter(tags=["reports"])

REPORT_MAP = {
    "clean": lambda p: p.clean_report_json,
    "chapters": lambda p: p.chapter_report_json,
    "chunks": lambda p: p.chunk_report_json,
    "extract": lambda p: p.extract_report_json,
    "normalize": lambda p: p.normalize_report_json,
}


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@router.get("/projects/{project_id}/reports/{report_name}")
def get_report(
    project_id: str,
    report_name: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    if report_name not in REPORT_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown report: {report_name}")
    paths = ProjectPaths(settings.data_root, project_id)
    path = REPORT_MAP[report_name](paths)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not available: {report_name}")
    return json.loads(path.read_text(encoding="utf-8"))
