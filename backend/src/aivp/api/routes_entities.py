import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.pipeline.normalize import apply_entity_merge

router = APIRouter(tags=["entities"])


class MergeBody(BaseModel):
    left: str
    right: str
    type: str = "character"
    accept: bool = True


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _load(path) -> Any:
    if not path.exists():
        return [] if "uncertain" in str(path) or "candidate" in str(path) else {}
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/projects/{project_id}/entities/uncertain")
def get_uncertain(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    return {
        "uncertain": _load(paths.uncertain_entities_json),
        "candidates": _load(paths.candidate_pairs_json),
        "entities": _load(paths.entities_json),
    }


@router.post("/projects/{project_id}/entities/merge")
def merge_entities(
    project_id: str,
    body: MergeBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    entities = _load(paths.entities_json)
    uncertain = _load(paths.uncertain_entities_json)
    if not isinstance(entities, dict):
        raise HTTPException(status_code=404, detail="entities not available")
    entities, uncertain = apply_entity_merge(
        entities,
        uncertain if isinstance(uncertain, list) else [],
        left=body.left,
        right=body.right,
        entity_type=body.type,
        accept=True,
    )
    paths.entities_json.write_text(
        json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.uncertain_entities_json.write_text(
        json.dumps(uncertain, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.candidate_pairs_json.write_text(
        json.dumps(uncertain, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"entities": entities, "uncertain": uncertain}


@router.post("/projects/{project_id}/entities/reject-merge")
def reject_merge(
    project_id: str,
    body: MergeBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    entities = _load(paths.entities_json)
    uncertain = _load(paths.uncertain_entities_json)
    entities, uncertain = apply_entity_merge(
        entities if isinstance(entities, dict) else {},
        uncertain if isinstance(uncertain, list) else [],
        left=body.left,
        right=body.right,
        entity_type=body.type,
        accept=False,
    )
    paths.uncertain_entities_json.write_text(
        json.dumps(uncertain, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.candidate_pairs_json.write_text(
        json.dumps(uncertain, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"entities": entities, "uncertain": uncertain}
