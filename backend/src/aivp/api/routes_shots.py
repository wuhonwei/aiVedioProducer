import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.pipeline.asset_plan import patch_asset_plan_entry
from aivp.pipeline.shot_upgrade import (
    build_asset_plan,
    build_name_to_id_map,
    save_asset_plan,
    upgrade_shot_document,
    upgrade_shot_to_v2,
    write_shot_script_index,
    write_shot_yamls,
)

router = APIRouter(tags=["shots"])

VALID_REVIEW = frozenset(
    {"needs_review", "approved", "rejected", "needs_regen", "locked"}
)


class ShotReviewBody(BaseModel):
    status: str = Field(
        description="needs_review|approved|rejected|needs_regen|locked"
    )
    note: str = ""


class AssetPlanPatchBody(BaseModel):
    status: str | None = None
    priority: str | None = None
    needs_lora: bool | None = None
    needs_concept_art: bool | None = None
    needs_reference: bool | None = None
    needs_reference_set: bool | None = None
    description: str | None = None
    appearance: str | None = None


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _load_entity_maps(paths: ProjectPaths) -> tuple[dict | None, dict | None]:
    entities = None
    assets = None
    if paths.entities_json.exists():
        entities = json.loads(paths.entities_json.read_text(encoding="utf-8"))
    if paths.assets_json.exists():
        assets = json.loads(paths.assets_json.read_text(encoding="utf-8"))
    return entities, assets


def _load_doc(paths: ProjectPaths) -> dict[str, Any]:
    if not paths.shot_script_json.exists():
        raise HTTPException(status_code=404, detail="Shot script not available yet")
    doc = json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
    entities, assets = _load_entity_maps(paths)
    return upgrade_shot_document(doc, name_to_id=build_name_to_id_map(assets, entities))


def _refresh_asset_plan(paths: ProjectPaths, doc: dict[str, Any], *, approved_only: bool = True) -> dict:
    entities, assets = _load_entity_maps(paths)
    plan = build_asset_plan(
        doc.get("shots") or [],
        approved_only=approved_only,
        entities=entities,
        assets=assets,
    )
    save_asset_plan(paths.asset_plan_json, plan)
    return plan


def _save_doc(
    paths: ProjectPaths,
    doc: dict[str, Any],
    *,
    refresh_plan: bool = False,
    approved_only_plan: bool = True,
) -> dict[str, Any]:
    entities, assets = _load_entity_maps(paths)
    doc = upgrade_shot_document(doc, name_to_id=build_name_to_id_map(assets, entities))
    paths.shot_script_dir.mkdir(parents=True, exist_ok=True)
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_shot_script_index(paths.shot_script_index_json, doc)
    if refresh_plan:
        _refresh_asset_plan(paths, doc, approved_only=approved_only_plan)
    return doc


@router.get("/projects/{project_id}/shots")
def get_shots(
    project_id: str,
    offset: int = 0,
    limit: int | None = None,
    event_id: str | None = None,
    chapter_id: str | None = None,
    review_status: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    shots = list(doc.get("shots") or [])
    if event_id:
        shots = [s for s in shots if s.get("event_id") == event_id]
    if chapter_id:
        shots = [s for s in shots if s.get("chapter_id") == chapter_id]
    if review_status:
        shots = [
            s
            for s in shots
            if (s.get("review_status") or ((s.get("review") or {}).get("status")))
            == review_status
        ]
    total = len(shots)
    if (
        limit is None
        and offset == 0
        and event_id is None
        and chapter_id is None
        and review_status is None
    ):
        return doc
    page_size = limit if limit is not None else settings.api_page_size
    page_size = max(1, min(int(page_size), 500))
    offset = max(0, int(offset))
    slice_ = shots[offset : offset + page_size]
    return {
        "schema_version": doc.get("schema_version"),
        "model": doc.get("model"),
        "event_count": doc.get("event_count"),
        "shot_count": total,
        "items": slice_,
        "shots": slice_,
        "offset": offset,
        "limit": page_size,
        "total_count": total,
        "has_more": offset + len(slice_) < total,
        "warnings": doc.get("warnings") or [],
        "volumes": doc.get("volumes") or [],
    }


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
        if shot.get("shot_id") != shot_id:
            continue
        unlock = (
            patch.get("review_status") == "needs_review"
            or (isinstance(patch.get("review"), dict) and patch["review"].get("status") == "needs_review")
            or patch.get("locked") is False
        )
        if (shot.get("locked") or shot.get("review_status") == "locked") and not unlock:
            raise HTTPException(status_code=409, detail="shot_locked")
        updated = {**shot, **patch, "shot_id": shot_id}
        if unlock:
            updated["locked"] = False
            if "review_status" not in patch:
                updated["review_status"] = "needs_review"
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
    if body.status not in VALID_REVIEW:
        raise HTTPException(status_code=400, detail=f"invalid_review_status:{body.status}")
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    found = None
    for i, shot in enumerate(doc.get("shots") or []):
        if shot.get("shot_id") != shot_id:
            continue
        review = dict(shot.get("review") or {})
        review["status"] = body.status
        if body.note:
            notes = list(review.get("notes") or [])
            notes.append(body.note)
            review["notes"] = notes
        shot["review"] = review
        shot["review_status"] = body.status
        shot["locked"] = body.status == "locked"
        doc["shots"][i] = upgrade_shot_to_v2(shot, shot.get("global_order") or i + 1)
        found = doc["shots"][i]
        break
    if found is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    _save_doc(paths, doc, refresh_plan=True, approved_only_plan=True)
    try:
        write_shot_yamls(paths.shots_dir, [found])
    except RuntimeError:
        pass
    return found


@router.post("/projects/{project_id}/shots/export-yaml")
def export_yaml(
    project_id: str,
    approved_only: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    try:
        written = write_shot_yamls(
            paths.shots_dir, doc.get("shots") or [], approved_only=approved_only
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _save_doc(paths, doc, refresh_plan=True, approved_only_plan=True)
    return {
        "count": len(written),
        "root": str(paths.shots_dir),
        "approved_only": approved_only,
    }


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
    return _refresh_asset_plan(paths, doc, approved_only=True)


@router.post("/projects/{project_id}/assets/plan/regenerate")
def regenerate_asset_plan(
    project_id: str,
    approved_only: bool = True,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    doc = _load_doc(paths)
    return _refresh_asset_plan(paths, doc, approved_only=approved_only)


@router.patch("/projects/{project_id}/assets/plan/{asset_type}/{asset_id}")
def patch_asset_plan(
    project_id: str,
    asset_type: str,
    asset_id: str,
    body: AssetPlanPatchBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    if not paths.asset_plan_json.exists():
        if not paths.shot_script_json.exists():
            raise HTTPException(status_code=404, detail="Asset plan not available yet")
        doc = _load_doc(paths)
        plan = _refresh_asset_plan(paths, doc, approved_only=True)
    else:
        plan = json.loads(paths.asset_plan_json.read_text(encoding="utf-8"))
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        plan = patch_asset_plan_entry(plan, asset_type, asset_id, patch)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    save_asset_plan(paths.asset_plan_json, plan)
    # Return the patched entry.
    key = asset_type if asset_type.endswith("s") else asset_type + "s"
    for item in plan.get(key) or []:
        if item.get("id") == asset_id or item.get("name") == asset_id:
            return item
    return plan
