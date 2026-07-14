import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.bible.export_md import export_version
from aivp.bible.overlay import apply_merge_patch, merge_bible
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths

router = APIRouter(tags=["bible"])


def _load_json(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@router.get("/projects/{project_id}/bible")
def get_bible(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    auto = _load_json(paths.auto_bible_json)
    overlay = _load_json(paths.overlay_json)
    if not auto and not overlay:
        raise HTTPException(status_code=404, detail="Story bible not available yet")
    return merge_bible(auto, overlay)


@router.patch("/projects/{project_id}/bible")
def patch_bible(
    project_id: str,
    patch: dict[str, Any],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    paths.ensure()
    overlay = _load_json(paths.overlay_json)
    updated = apply_merge_patch(overlay, patch)
    paths.overlay_json.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    auto = _load_json(paths.auto_bible_json)
    return merge_bible(auto, updated)


@router.post("/projects/{project_id}/exports")
def create_export(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    project = _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    auto = _load_json(paths.auto_bible_json)
    overlay = _load_json(paths.overlay_json)
    if not auto and not overlay:
        raise HTTPException(status_code=404, detail="Story bible not available yet")
    bible = merge_bible(auto, overlay)
    version = int(project.export_version or 0) + 1
    written = export_version(paths.exports_dir, bible, version)
    project.export_version = version
    db.commit()
    return {
        "version": version,
        "json": str(written["json"]),
        "md": str(written["md"]),
    }
