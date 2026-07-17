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
from aivp.visual.look_lock import clear_look_lock, set_look_lock
from aivp.visual.lora_train import execute_lora_train, export_train_package, run_lora_train
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import (
    build_lora_refs,
    character_status,
    ensure_profile,
    load_major_characters,
)
from aivp.visual.sheets import generate_character_sheets
from aivp.visual.t2i import approve_lora, generate_with_character, reject_lora
from aivp.visual.trainset_check import check_trainset

_VISUAL_FOLDERS = frozenset(
    {"candidates", "curated", "generations", "lora", "sheets", "look_lock"}
)

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
    count: int = Field(default=8, ge=1, le=100)


class CurateBody(BaseModel):
    keep: list[str] = Field(default_factory=list)
    keep_sheets: list[str] = Field(default_factory=list)


class TrainBody(BaseModel):
    character_ids: list[str] | None = None


class T2IBody(BaseModel):
    character_id: str
    prompt: str = ""
    shot_id: str | None = None
    is_probe: bool = False


class ProbeRejectBody(BaseModel):
    note: str = ""


class LookLockBody(BaseModel):
    folder: str
    filename: str
    denoise: float = 0.48


class SheetsBody(BaseModel):
    character_id: str
    # all | turnaround | expression — ignored when slot_keys set
    group: str = "all"
    # e.g. ["turnaround_front"] or ["expr_calm"] for single-shot
    slot_keys: list[str] | None = None


@router.get("/projects/{project_id}/visual/sheet-slots")
def list_sheet_slots(
    project_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.prompts import EXPRESSION_SLOTS, TURNAROUND_SLOTS

    return {
        "turnaround": [
            {"key": k, "label": lab} for k, lab, _ in TURNAROUND_SLOTS
        ],
        "expression": [
            {"key": k, "label": lab} for k, lab, _ in EXPRESSION_SLOTS
        ],
    }


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
    return curate_candidates(
        vpaths,
        character_id,
        body.keep,
        keep_sheets=body.keep_sheets,
    )


@router.get("/projects/{project_id}/visual/characters/{character_id}/trainset/check")
def trainset_check(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    return check_trainset(vpaths, character_id)


@router.post("/projects/{project_id}/visual/characters/{character_id}/lora/package")
def package_lora_character(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return export_train_package(vpaths, character_id, require_can_train=True)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/projects/{project_id}/visual/lora/package")
def package_lora_batch(
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
        try:
            results.append(export_train_package(vpaths, cid, require_can_train=True))
        except (FileNotFoundError, ValueError) as e:
            results.append({"character_id": cid, "packaged": False, "error": str(e)})
    return {"results": results}


@router.post(
    "/projects/{project_id}/visual/characters/{character_id}/lora/train",
    status_code=202,
)
def start_lora_train_character(
    project_id: str,
    character_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    if not (getattr(settings, "lora_train_cmd", "") or ""):
        raise HTTPException(status_code=400, detail="lora_train_cmd_not_configured")
    vpaths = VisualPaths(settings.data_root, project_id)
    package = vpaths.lora_dir(character_id) / "train_package.json"
    if not package.exists():
        raise HTTPException(status_code=400, detail="train_package_missing; export package first")
    check = check_trainset(vpaths, character_id)
    if not check.get("can_train"):
        raise HTTPException(status_code=400, detail=f"trainset_not_ready:{check.get('warnings')}")

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "lora_train",
        "character_id": character_id,
        "status": "queued",
        "progress_done": 0,
        "progress_total": 1,
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
            result = execute_lora_train(vpaths, character_id, settings)
            data["progress_done"] = 1
            if result.get("trained"):
                data["status"] = "succeeded"
            else:
                data["status"] = "failed"
                data["error"] = result.get("stderr") or result.get("train_error") or "train_failed"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(target=_worker, daemon=False, name=f"aivp-lora-{job_id}").start()
    return job


@router.post("/projects/{project_id}/visual/lora/train")
def train_lora(
    project_id: str,
    body: TrainBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Legacy sync entry: export package; train if cmd configured."""
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


@router.post("/projects/{project_id}/visual/characters/{character_id}/lora/probe")
def probe_lora(
    project_id: str,
    character_id: str,
    body: T2IBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    backend = get_image_backend(settings)
    prompt = (body.prompt if body else "") or ""
    return generate_with_character(
        vpaths,
        character_id,
        prompt,
        backend,
        shot_id=(body.shot_id if body else None) or "probe",
        is_probe=True,
    )


@router.post("/projects/{project_id}/visual/characters/{character_id}/lora/approve")
def approve_lora_endpoint(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return approve_lora(vpaths, character_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/projects/{project_id}/visual/characters/{character_id}/lora/reject")
def reject_lora_endpoint(
    project_id: str,
    character_id: str,
    body: ProbeRejectBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return reject_lora(vpaths, character_id, note=(body.note if body else ""))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/projects/{project_id}/visual/lora-refs")
def get_lora_refs(
    project_id: str,
    character_ids: str = "",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    ids = [c.strip() for c in character_ids.split(",") if c.strip()]
    refs, warnings = build_lora_refs(vpaths, ids, only_ready=True)
    return {"lora_refs": refs, "warnings": warnings}


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
        is_probe=bool(body.is_probe),
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
                group=body.group,
                slot_keys=body.slot_keys,
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


@router.put("/projects/{project_id}/visual/characters/{character_id}/look-lock")
def put_look_lock(
    project_id: str,
    character_id: str,
    body: LookLockBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return set_look_lock(
            vpaths,
            character_id,
            folder=body.folder,
            filename=body.filename,
            denoise=body.denoise,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/projects/{project_id}/visual/characters/{character_id}/look-lock")
def delete_look_lock(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return clear_look_lock(vpaths, character_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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
    headers = None
    if folder == "look_lock":
        # ref.png is overwritten in place; prevent browsers from keeping the old preview.
        headers = {"Cache-Control": "no-store, max-age=0"}
    return FileResponse(path, headers=headers)


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
    # Clear look-lock pointer if the source image was deleted (ref copy remains until cleared).
    profile_path = vpaths.profile_json(character_id)
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
        if lock and lock.get("folder") == folder and lock.get("file") == filename:
            # Keep ref.png; only mark source missing in metadata.
            lock["source_missing"] = True
            profile["look_lock"] = lock
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    return {"deleted": True, "folder": folder, "filename": filename}


class SelfCheckBody(BaseModel):
    character_ids: list[str] | None = None
    candidate_count: int = Field(default=4, ge=1, le=16)
    max_rounds: int | None = None
    pass_rate: float | None = None
    apply_patches: bool = True
    judge_only: bool = False


@router.post("/projects/{project_id}/visual/self-check", status_code=202)
def start_visual_self_check(
    project_id: str,
    request: Request,
    body: SelfCheckBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Generate (optional) + vision-judge images; auto-write qa_tuning until pass rate OK."""
    _require_project(db, project_id)
    body = body or SelfCheckBody()
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "visual_self_check",
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
            from aivp.llm.ollama_vision_client import OllamaVisionClient
            from aivp.visual.self_check import (
                evaluate_character_images,
                resolve_major_characters,
                run_self_check_loop,
            )

            vision = OllamaVisionClient(settings.ollama_base_url, settings.ollama_vision_model)
            if not vision.model_available():
                raise RuntimeError(
                    f"vision_model_missing:{settings.ollama_vision_model}; "
                    f"run `ollama pull {settings.ollama_vision_model}`"
                )
            threshold = (
                float(body.pass_rate)
                if body.pass_rate is not None
                else float(settings.visual_qa_pass_rate)
            )
            if body.judge_only:
                bible = _load_bible(settings, project_id)
                bible_chars = resolve_major_characters(
                    vpaths, bible=bible, character_ids=body.character_ids
                )
                reports = [
                    evaluate_character_images(vpaths, ch, vision) for ch in bible_chars
                ]
                result = {
                    "mode": "judge_only",
                    "pass_rate_threshold": threshold,
                    "reports": reports,
                }
            else:
                backend = get_image_backend(settings)
                bible = _load_bible(settings, project_id)
                result = run_self_check_loop(
                    vpaths,
                    backend,
                    vision,
                    bible=bible,
                    character_ids=body.character_ids,
                    pass_rate_threshold=threshold,
                    max_rounds=int(body.max_rounds or settings.visual_qa_max_rounds),
                    candidate_count=body.candidate_count,
                    apply_patches=body.apply_patches,
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
        threading.Thread(target=_worker, daemon=False, name=f"aivp-selfcheck-{job_id}").start()
    return job

