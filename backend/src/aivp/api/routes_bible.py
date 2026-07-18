import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aivp.api.deps import get_db, get_settings
from aivp.bible.export_md import export_version
from aivp.bible.expression_rebuild import (
    load_enrich_events,
    rebuild_all_major_expression_dims,
    rebuild_character_expression_dims,
    write_characters_overlay,
)
from aivp.bible.meta import (
    ensure_bible_meta,
    persist_merged_bible,
    set_block_lock,
    set_block_review,
)
from aivp.bible.overlay import apply_merge_patch, merge_bible
from aivp.config import Settings
from aivp.models import Project
from aivp.paths import ProjectPaths
from aivp.schemas import REQUIRED_BIBLE_KEYS

router = APIRouter(tags=["bible"])


class ReviewBody(BaseModel):
    block: str
    action: str = Field(description="approve|reject|needs_review|draft")
    note: str = ""


class LockBody(BaseModel):
    block: str
    locked: bool = True


class ExpressionDimsRebuildBody(BaseModel):
    character_ids: list[str] = Field(default_factory=list)
    max_dims: int = 8


def _load_json(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _persist(paths: ProjectPaths) -> tuple[dict[str, Any], dict[str, Any]]:
    return persist_merged_bible(
        auto_path=paths.auto_bible_json,
        overlay_path=paths.overlay_json,
        merged_path=paths.merged_bible_json,
        meta_path=paths.bible_meta_json,
    )


@router.get("/projects/{project_id}/bible")
def get_bible(
    project_id: str,
    sections: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    auto = _load_json(paths.auto_bible_json)
    overlay = _load_json(paths.overlay_json)
    if not auto and not overlay:
        raise HTTPException(status_code=404, detail="Story bible not available yet")
    merged, _meta = _persist(paths)
    if sections:
        keys = [k.strip() for k in sections.split(",") if k.strip()]
        out = {k: merged.get(k) for k in keys if k in merged or k in REQUIRED_BIBLE_KEYS}
        if "timeline" in keys:
            preview = _timeline_preview_fields(paths, settings, merged)
            out["timeline"] = preview["timeline"]
            out["timeline_ref"] = preview["timeline_ref"]
        return out
    # Never inline a huge timeline into Bible GET — clients page via /timeline.
    preview = _timeline_preview_fields(paths, settings, merged)
    return {**merged, **preview}


def _timeline_preview_fields(
    paths: ProjectPaths,
    settings: Settings,
    merged: dict[str, Any],
) -> dict[str, Any]:
    page_size = max(1, int(settings.timeline_page_size or 50))
    events: list[Any] = []
    if paths.events_json.exists():
        try:
            events = json.loads(paths.events_json.read_text(encoding="utf-8"))
            if not isinstance(events, list):
                events = []
        except (OSError, json.JSONDecodeError):
            events = []
    if not events and isinstance(merged.get("timeline"), list):
        events = list(merged.get("timeline") or [])
    total = len(events)
    ref = merged.get("timeline_ref") if isinstance(merged.get("timeline_ref"), dict) else {}
    if total == 0 and isinstance(ref.get("total_count"), int):
        total = int(ref["total_count"])
    preview = events[:page_size] if events else list(merged.get("timeline") or [])[:page_size]
    return {
        "timeline": preview,
        "timeline_ref": {
            "total_count": total or int(ref.get("total_count") or len(preview)),
            "page_size": page_size,
            "preview_count": len(preview),
            "paged_via": f"/api/projects/.../timeline?offset=&limit=",
        },
    }


@router.get("/projects/{project_id}/timeline")
def get_timeline(
    project_id: str,
    offset: int = 0,
    limit: int | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    page_size = limit if limit is not None else settings.api_page_size
    page_size = max(1, min(int(page_size), 500))
    offset = max(0, int(offset))

    events: list[dict[str, Any]] = []
    if paths.events_json.exists():
        events = json.loads(paths.events_json.read_text(encoding="utf-8"))
    elif paths.timeline_index_json.exists() and paths.timeline_pages_dir.exists():
        index = json.loads(paths.timeline_index_json.read_text(encoding="utf-8"))
        for page_meta in index.get("pages") or []:
            page_path = paths.timeline_pages_dir / page_meta["path"]
            if page_path.exists():
                events.extend(json.loads(page_path.read_text(encoding="utf-8")))
    else:
        raise HTTPException(status_code=404, detail="Timeline not available yet")

    total = len(events)
    slice_ = events[offset : offset + page_size]
    return {
        "items": slice_,
        "offset": offset,
        "limit": page_size,
        "total_count": total,
        "has_more": offset + len(slice_) < total,
    }


@router.get("/projects/{project_id}/bible/meta")
def get_bible_meta(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    if not paths.auto_bible_json.exists() and not paths.overlay_json.exists():
        raise HTTPException(status_code=404, detail="Story bible not available yet")
    _, meta = _persist(paths)
    return meta


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
    meta = ensure_bible_meta(_load_json(paths.bible_meta_json) or None)
    for key in patch:
        if key in REQUIRED_BIBLE_KEYS and meta["blocks"].get(key, {}).get("locked"):
            raise HTTPException(status_code=409, detail=f"Block locked: {key}")
    overlay = _load_json(paths.overlay_json)
    updated = apply_merge_patch(overlay, patch)
    paths.overlay_json.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    merged, _ = _persist(paths)
    return merged


@router.post("/projects/{project_id}/bible/review")
def review_bible_block(
    project_id: str,
    body: ReviewBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    if body.block not in REQUIRED_BIBLE_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown block: {body.block}")
    paths = ProjectPaths(settings.data_root, project_id)
    meta = ensure_bible_meta(_load_json(paths.bible_meta_json) or None)
    try:
        meta = set_block_review(meta, block=body.block, action=body.action, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    paths.bible_meta_json.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


@router.post("/projects/{project_id}/bible/lock")
def lock_bible_block(
    project_id: str,
    body: LockBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    if body.block not in REQUIRED_BIBLE_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown block: {body.block}")
    paths = ProjectPaths(settings.data_root, project_id)
    meta = ensure_bible_meta(_load_json(paths.bible_meta_json) or None)
    # Snapshot current merged content into overlay when locking so auto can't wipe it.
    if body.locked:
        merged, _ = _persist(paths)
        overlay = _load_json(paths.overlay_json)
        overlay[body.block] = merged.get(body.block)
        paths.overlay_json.write_text(
            json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    meta = set_block_lock(meta, block=body.block, locked=body.locked)
    paths.bible_meta_json.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _persist(paths)
    return meta


@router.post("/projects/{project_id}/bible/expression-dims/rebuild")
def rebuild_expression_dims_batch(
    project_id: str,
    body: ExpressionDimsRebuildBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Cluster story emotions into expression_dims for major characters (merge mode)."""
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    paths.ensure()
    body = body or ExpressionDimsRebuildBody()
    merged, _ = _persist(paths)
    events = load_enrich_events(paths)
    updated = rebuild_all_major_expression_dims(
        merged,
        events,
        character_ids=body.character_ids or None,
        max_dims=max(1, min(int(body.max_dims or 8), 16)),
    )
    write_characters_overlay(paths, list(updated.get("characters") or []))
    merged2, _ = _persist(paths)
    chars = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "dim_count": len(c.get("expression_dims") or []),
            "expression_dims": c.get("expression_dims") or [],
        }
        for c in (merged2.get("characters") or [])
        if isinstance(c, dict)
        and (
            not body.character_ids
            or c.get("id") in body.character_ids
            or str(c.get("tier") or "") == "major"
        )
    ]
    if body.character_ids:
        want = set(body.character_ids)
        chars = [c for c in chars if c.get("id") in want]
    else:
        # Only report majors when batching all.
        id_to_tier = {
            str(c.get("id")): str(c.get("tier") or "major")
            for c in (merged2.get("characters") or [])
            if isinstance(c, dict)
        }
        chars = [c for c in chars if id_to_tier.get(str(c.get("id"))) == "major"]
    return {"updated": len(chars), "characters": chars, "events_used": len(events)}


@router.post(
    "/projects/{project_id}/bible/characters/{character_id}/expression-dims/rebuild"
)
def rebuild_expression_dims_one(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    paths.ensure()
    merged, _ = _persist(paths)
    events = load_enrich_events(paths)
    chars = list(merged.get("characters") or [])
    found = None
    out_chars: list[dict[str, Any]] = []
    for ch in chars:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("id")) == character_id:
            found = rebuild_character_expression_dims(ch, events)
            out_chars.append(found)
        else:
            out_chars.append(ch)
    if found is None:
        raise HTTPException(status_code=404, detail=f"character_not_found:{character_id}")
    write_characters_overlay(paths, out_chars)
    _persist(paths)
    return {
        "character_id": character_id,
        "expression_dims": found.get("expression_dims") or [],
        "events_used": len(events),
    }


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
    bible, _ = _persist(paths)
    version = int(project.export_version or 0) + 1
    export_version(paths.exports_dir, bible, version)
    project.export_version = version
    db.commit()
    return {
        "version": version,
        "json_url": f"/api/projects/{project_id}/exports/{version}/json",
        "md_url": f"/api/projects/{project_id}/exports/{version}/md",
        "pack_dir": f"story_bible.v{version:03d}_pack",
    }


def _export_file(paths: ProjectPaths, version: int, ext: str) -> FileResponse:
    path = paths.exports_dir / f"story_bible.v{version:03d}.{ext}"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Export v{version:03d} not found")
    media_type = "application/json" if ext == "json" else "text/markdown"
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/projects/{project_id}/exports/{version}/json")
def get_export_json(
    project_id: str,
    version: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    return _export_file(paths, version, "json")


@router.get("/projects/{project_id}/exports/{version}/md")
def get_export_md(
    project_id: str,
    version: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_project(db, project_id)
    paths = ProjectPaths(settings.data_root, project_id)
    return _export_file(paths, version, "md")
