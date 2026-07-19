from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
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
    read_profile_json,
    save_profile,
)
from aivp.visual.sheets import generate_character_sheets
from aivp.visual.t2i import (
    approve_lora,
    generate_shot_with_loras,
    generate_with_character,
    reject_lora,
)
from aivp.visual.trainset_check import check_trainset

_VISUAL_FOLDERS = frozenset(
    {
        "candidates",
        "curated",
        "generations",
        "lora",
        "sheets",
        "look_lock",
        "look_lock_archive",
    }
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


class BatchTrainBody(BaseModel):
    """Train many characters sequentially (one LoRA each)."""

    character_ids: list[str] | None = None
    # If true, export packages for can_train characters before training.
    auto_package: bool = True


class T2IBody(BaseModel):
    character_id: str | None = None
    character_ids: list[str] = []
    location_id: str | None = None
    prompt: str = ""
    shot_id: str | None = None
    is_probe: bool = False
    use_location_lora: bool = False


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
) -> JSONResponse:
    _require_project(db, project_id)
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    items = []
    for ch in load_major_characters(bible):
        profile = ensure_profile(vpaths, ch)
        status = character_status(vpaths, profile["character_id"], profile)
        dims = ch.get("expression_dims") if isinstance(ch.get("expression_dims"), list) else []
        status["expression_dims"] = dims
        status["default_expression"] = ch.get("default_expression") or profile.get(
            "default_expression"
        )
        items.append(status)
    return JSONResponse(
        content={
            "characters": items,
            "backend": settings.image_backend,
            "lora_train_configured": bool(getattr(settings, "lora_train_cmd", "") or ""),
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/projects/{project_id}/visual/locations")
def list_visual_locations(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    _require_project(db, project_id)
    from aivp.visual.location_profiles import (
        ensure_location_profile,
        load_major_locations,
        location_status,
    )

    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    items = []
    for loc in load_major_locations(bible):
        profile = ensure_location_profile(vpaths, loc)
        items.append(location_status(vpaths, profile["location_id"], profile))
    return JSONResponse(
        content={
            "locations": items,
            "backend": settings.image_backend,
            "lora_train_configured": bool(getattr(settings, "lora_train_cmd", "") or ""),
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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
                if total > 0 and done < total:
                    data["progress_note"] = f"正在生成第 {done + 1}/{total} 张"
                elif total > 0:
                    data["progress_note"] = f"已完成 {done}/{total}"
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
            data["progress_note"] = None
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            data["progress_note"] = None
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
) -> JSONResponse:
    _require_project(db, project_id)
    path = _job_path(VisualPaths(settings.data_root, project_id), job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="visual job not found")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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
    bible = _load_bible(settings, project_id)
    ch = next(
        (
            c
            for c in (bible.get("characters") or [])
            if isinstance(c, dict) and str(c.get("id")) == character_id
        ),
        None,
    )
    dims = ch.get("expression_dims") if isinstance(ch, dict) else None
    dim_count = None
    if isinstance(dims, list):
        dim_count = len(
            [
                d
                for d in dims
                if isinstance(d, dict)
                and str(d.get("status") or "") not in {"rejected", "stale"}
            ]
        )
    return check_trainset(vpaths, character_id, expression_dim_count=dim_count)


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
        "progress_note": "微调任务已排队…",
        "error": None,
        "result": None,
    }
    path = _job_path(vpaths, job_id)
    _write_job(path, job)

    def _worker() -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "running"
        data["progress_note"] = "正在启动 LoRA 微调…"
        _write_job(path, data)

        def on_progress(done: int, total: int, note: str | None = None) -> None:
            data["progress_done"] = done
            data["progress_total"] = total
            if note:
                data["progress_note"] = note
            _write_job(path, data)

        try:
            result = execute_lora_train(
                vpaths, character_id, settings, on_progress=on_progress
            )
            data["progress_done"] = 1
            data["progress_total"] = 1
            if result.get("trained"):
                data["status"] = "succeeded"
                data["progress_note"] = "微调完成，请试生成验证"
            else:
                data["status"] = "failed"
                data["error"] = result.get("stderr") or result.get("train_error") or "train_failed"
                data["progress_note"] = "微调失败"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            data["progress_note"] = "微调失败"
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(target=_worker, daemon=False, name=f"aivp-lora-{job_id}").start()
    return job


def _existing_lora_weights(vpaths: VisualPaths, character_id: str, profile: dict) -> list[Path]:
    """Return on-disk LoRA .safetensors for this character (project lora/ only)."""
    lora_dir = vpaths.lora_dir(character_id)
    named = profile.get("lora_file")
    found: list[Path] = []
    if isinstance(named, str) and named.strip():
        path = lora_dir / Path(named).name
        if path.is_file():
            found.append(path)
    for path in sorted(lora_dir.glob("*.safetensors")):
        if path.is_file() and path not in found:
            found.append(path)
    return found


def _batch_train_skip_reason(
    vpaths: VisualPaths, character_id: str, profile: dict
) -> str | None:
    """Skip characters that already have a finished LoRA (or are mid-train)."""
    status = str(profile.get("train_status") or "")
    if status == "training":
        return "already_training"
    weights = _existing_lora_weights(vpaths, character_id, profile)
    if not weights:
        return None
    if status == "trained" or bool(profile.get("lora_ready")):
        return "already_trained"
    return None


def _resolve_batch_train_targets(
    vpaths: VisualPaths,
    majors: list[dict],
    *,
    auto_package: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (ready_to_train items, skipped items)."""
    ready: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for ch in majors:
        cid = str(ch.get("id") or "")
        name = str(ch.get("name") or cid)
        profile = ensure_profile(vpaths, ch)
        skip_reason = _batch_train_skip_reason(vpaths, cid, profile)
        if skip_reason:
            weights = _existing_lora_weights(vpaths, cid, profile)
            skipped.append(
                {
                    "character_id": cid,
                    "name": name,
                    "status": "skipped",
                    "error": skip_reason,
                    "lora_file": weights[0].name if weights else profile.get("lora_file"),
                }
            )
            continue
        package = vpaths.lora_dir(cid) / "train_package.json"
        check = check_trainset(vpaths, cid)
        if auto_package and not package.exists():
            if not check.get("can_train"):
                skipped.append(
                    {
                        "character_id": cid,
                        "name": name,
                        "status": "skipped",
                        "error": f"trainset_not_ready:{check.get('warnings')}",
                    }
                )
                continue
            try:
                export_train_package(vpaths, cid, require_can_train=True)
                package = vpaths.lora_dir(cid) / "train_package.json"
            except (FileNotFoundError, ValueError) as exc:
                skipped.append(
                    {
                        "character_id": cid,
                        "name": name,
                        "status": "skipped",
                        "error": f"package_failed:{exc}",
                    }
                )
                continue
        if not package.exists():
            skipped.append(
                {
                    "character_id": cid,
                    "name": name,
                    "status": "skipped",
                    "error": "train_package_missing",
                }
            )
            continue
        ready.append(
            {
                "character_id": cid,
                "name": name,
                "status": "queued",
                "error": None,
                "lora_file": None,
            }
        )
    return ready, skipped


@router.post("/projects/{project_id}/visual/lora/train/batch", status_code=202)
def start_lora_train_batch(
    project_id: str,
    request: Request,
    body: BatchTrainBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Queue sequential LoRA training for all package-ready majors (or given ids)."""
    _require_project(db, project_id)
    if not (getattr(settings, "lora_train_cmd", "") or ""):
        raise HTTPException(status_code=400, detail="lora_train_cmd_not_configured")
    body = body or BatchTrainBody()
    bible = _load_bible(settings, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    majors = load_major_characters(bible)
    if body.character_ids:
        want = set(body.character_ids)
        majors = [c for c in majors if c.get("id") in want]

    ready, skipped = _resolve_batch_train_targets(
        vpaths, majors, auto_package=bool(body.auto_package)
    )
    if not ready:
        already = sum(
            1
            for s in skipped
            if str(s.get("error") or "").startswith("already_")
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"no_characters_ready_to_train; skipped={len(skipped)}"
                + (f"; already_trained_or_training={already}" if already else "")
            ),
        )

    job_id = uuid.uuid4().hex[:12]
    items = list(ready)
    already_n = sum(
        1 for s in skipped if str(s.get("error") or "") in {"already_trained", "already_training"}
    )
    note = f"批量微调已排队：共 {len(items)} 个角色"
    if already_n:
        note += f"（已跳过 {already_n} 个已训练/训练中）"
    elif skipped:
        note += f"（另跳过 {len(skipped)} 个未就绪）"
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "lora_train_batch",
        "status": "queued",
        "progress_done": 0,
        "progress_total": len(items),
        "progress_note": note,
        "current_character_id": None,
        "items": items,
        "skipped": skipped,
        "error": None,
        "result": None,
    }
    path = _job_path(vpaths, job_id)
    _write_job(path, job)

    def _worker() -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "running"
        data["progress_note"] = "批量微调开始…"
        _write_job(path, data)
        results: list[dict[str, Any]] = []
        failed = 0
        for idx, item in enumerate(list(data.get("items") or [])):
            cid = str(item.get("character_id") or "")
            name = str(item.get("name") or cid)
            data["current_character_id"] = cid
            data["items"][idx]["status"] = "running"
            data["progress_note"] = (
                f"正在微调 {name}（{idx + 1}/{len(data['items'])}）…"
            )
            _write_job(path, data)

            def on_progress(
                done: int,
                total: int,
                note: str | None = None,
                *,
                _idx: int = idx,
                _name: str = name,
                _n: int = len(data["items"]),
            ) -> None:
                # Keep character-level counters; surface trainer heartbeat in note.
                prefix = f"[{_idx + 1}/{_n}] {_name}"
                data["progress_note"] = f"{prefix} · {note}" if note else prefix
                _write_job(path, data)

            try:
                result = execute_lora_train(
                    vpaths, cid, settings, on_progress=on_progress
                )
                ok = bool(result.get("trained"))
                data["items"][idx]["status"] = "succeeded" if ok else "failed"
                data["items"][idx]["lora_file"] = result.get("lora_file")
                data["items"][idx]["error"] = None if ok else (
                    result.get("stderr") or result.get("train_error") or "train_failed"
                )
                if not ok:
                    failed += 1
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                data["items"][idx]["status"] = "failed"
                data["items"][idx]["error"] = str(exc)
                results.append({"character_id": cid, "trained": False, "error": str(exc)})
            data["progress_done"] = idx + 1
            data["progress_note"] = (
                f"已完成 {idx + 1}/{len(data['items'])}："
                f"{data['items'][idx]['status']} · {name}"
            )
            _write_job(path, data)

        data["current_character_id"] = None
        data["result"] = {"results": results, "failed": failed, "total": len(items)}
        if failed == 0:
            data["status"] = "succeeded"
            data["progress_note"] = f"批量微调全部完成（{len(items)}）"
        elif failed == len(items):
            data["status"] = "failed"
            data["error"] = f"all_failed:{failed}"
            data["progress_note"] = f"批量微调全部失败（{failed}）"
        else:
            # Partial success still useful — mark succeeded with warning.
            data["status"] = "succeeded"
            data["error"] = f"partial_failed:{failed}"
            data["progress_note"] = (
                f"批量微调结束：成功 {len(items) - failed}，失败 {failed}"
            )
        _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(
            target=_worker, daemon=False, name=f"aivp-lora-batch-{job_id}"
        ).start()
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
        settings=settings,
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
    char_ids = list(body.character_ids or [])
    if not char_ids and body.character_id:
        char_ids = [body.character_id]
    use_shot_stack = (not body.is_probe) and (
        bool(body.location_id) or bool(body.character_ids)
    )
    if use_shot_stack:
        try:
            return generate_shot_with_loras(
                vpaths,
                backend,
                prompt=body.prompt,
                location_id=body.location_id,
                character_ids=char_ids or None,
                shot_id=body.shot_id,
                use_location_lora=bool(body.use_location_lora),
                settings=settings,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if not body.character_id:
        raise HTTPException(status_code=400, detail="character_id_required")
    return generate_with_character(
        vpaths,
        body.character_id,
        body.prompt,
        backend,
        shot_id=body.shot_id,
        is_probe=bool(body.is_probe),
        settings=settings,
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
    profile = read_profile_json(vpaths.profile_json(character_id))
    if profile:
        lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
        if lock and lock.get("folder") == folder and lock.get("file") == filename:
            # Keep ref.png; only mark source missing in metadata.
            lock["source_missing"] = True
            profile["look_lock"] = lock
            save_profile(vpaths, profile)
    return {"deleted": True, "folder": folder, "filename": filename}


class SelfCheckBody(BaseModel):
    character_ids: list[str] | None = None
    candidate_count: int = Field(default=4, ge=1, le=16)
    max_rounds: int | None = None
    pass_rate: float | None = None
    apply_patches: bool = True
    judge_only: bool = False


class BootstrapBody(BaseModel):
    character_ids: list[str] | None = None


class BootstrapSwapBody(BaseModel):
    filename: str
    folder: str = "look_lock_archive"
    denoise: float | None = None


@router.post("/projects/{project_id}/visual/bootstrap", status_code=202)
def start_visual_bootstrap(
    project_id: str,
    request: Request,
    body: BootstrapBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Auto look-lock + curated trainset; stops at awaiting_confirm (no LoRA train)."""
    _require_project(db, project_id)
    body = body or BootstrapBody()
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "visual_bootstrap",
        "status": "queued",
        "progress_done": 0,
        "progress_total": 0,
        "progress_note": None,
        "current_character_id": None,
        "bootstrap_step": None,
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
            from aivp.visual.bootstrap import bootstrap_project

            bible = _load_bible(settings, project_id)
            backend = get_image_backend(settings)
            vision = None
            # Stub PNGs are not meaningful for vision models; unit/API tests use stub.
            if (settings.image_backend or "").lower() != "stub":
                try:
                    client = OllamaVisionClient(
                        settings.ollama_base_url, settings.ollama_vision_model
                    )
                    if client.model_available():
                        vision = client
                except Exception:  # noqa: BLE001
                    vision = None
            entities = ProjectPaths(settings.data_root, project_id).entities_json

            def on_progress(payload: dict[str, Any]) -> None:
                data["current_character_id"] = payload.get("character_id")
                data["bootstrap_step"] = payload.get("step")
                msg = payload.get("message") or payload.get("step") or ""
                data["progress_note"] = str(msg) if msg else None
                if payload.get("done") is not None:
                    data["progress_done"] = int(payload["done"])
                if payload.get("total") is not None:
                    data["progress_total"] = int(payload["total"])
                _write_job(path, data)

            result = bootstrap_project(
                vpaths,
                bible,
                backend,
                settings=settings,
                vision=vision,
                llm=getattr(request.app.state, "llm", None),
                entities_json=entities if entities.exists() else None,
                character_ids=body.character_ids,
                on_progress=on_progress,
            )
            data["status"] = "succeeded"
            data["progress_note"] = "待人工确认训练集"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            data["progress_note"] = None
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(
            target=_worker, daemon=False, name=f"aivp-bootstrap-{job_id}"
        ).start()
    return job


@router.post(
    "/projects/{project_id}/visual/characters/{character_id}/bootstrap/confirm"
)
def confirm_visual_bootstrap(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.bootstrap import confirm_bootstrap

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return confirm_bootstrap(vpaths, character_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/projects/{project_id}/visual/characters/{character_id}/bootstrap/skip")
def skip_visual_bootstrap(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.bootstrap import skip_bootstrap

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return skip_bootstrap(vpaths, character_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/visual/characters/{character_id}/bootstrap/swap-look-lock"
)
def swap_visual_bootstrap_look_lock(
    project_id: str,
    character_id: str,
    body: BootstrapSwapBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.bootstrap import swap_look_lock

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return swap_look_lock(
            vpaths,
            character_id,
            filename=body.filename,
            folder=body.folder,
            denoise=body.denoise,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class LocationBootstrapBody(BaseModel):
    location_ids: list[str] | None = None


@router.post("/projects/{project_id}/visual/locations/bootstrap", status_code=202)
def start_visual_location_bootstrap(
    project_id: str,
    request: Request,
    body: LocationBootstrapBody | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Auto establishing lock + empty curated set; stops at awaiting_confirm."""
    _require_project(db, project_id)
    body = body or LocationBootstrapBody()
    vpaths = VisualPaths(settings.data_root, project_id)
    vpaths.ensure()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "project_id": project_id,
        "kind": "visual_location_bootstrap",
        "status": "queued",
        "progress_done": 0,
        "progress_total": 0,
        "progress_note": None,
        "current_location_id": None,
        "bootstrap_step": None,
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
            from aivp.visual.location_bootstrap import bootstrap_locations_project

            bible = _load_bible(settings, project_id)
            backend = get_image_backend(settings)
            vision = None
            if (settings.image_backend or "").lower() != "stub":
                try:
                    client = OllamaVisionClient(
                        settings.ollama_base_url, settings.ollama_vision_model
                    )
                    if client.model_available():
                        vision = client
                except Exception:  # noqa: BLE001
                    vision = None
            entities = ProjectPaths(settings.data_root, project_id).entities_json

            def on_progress(payload: dict[str, Any]) -> None:
                data["current_location_id"] = payload.get("location_id")
                data["bootstrap_step"] = payload.get("step")
                msg = payload.get("message") or payload.get("step") or ""
                data["progress_note"] = str(msg) if msg else None
                if payload.get("done") is not None:
                    data["progress_done"] = int(payload["done"])
                if payload.get("total") is not None:
                    data["progress_total"] = int(payload["total"])
                _write_job(path, data)

            result = bootstrap_locations_project(
                vpaths,
                bible,
                backend,
                settings=settings,
                vision=vision,
                llm=getattr(request.app.state, "llm", None),
                entities_json=entities if entities.exists() else None,
                location_ids=body.location_ids,
                on_progress=on_progress,
            )
            data["status"] = "succeeded"
            data["progress_note"] = "待人工确认地点训练集"
            data["result"] = result
            _write_job(path, data)
        except Exception as e:  # noqa: BLE001
            data["status"] = "failed"
            data["error"] = str(e)
            data["progress_note"] = None
            _write_job(path, data)

    if getattr(request.app.state, "run_jobs_inline", False):
        _worker()
    else:
        threading.Thread(
            target=_worker, daemon=False, name=f"aivp-loc-bootstrap-{job_id}"
        ).start()
    return job


@router.post(
    "/projects/{project_id}/visual/locations/{location_id}/bootstrap/confirm"
)
def confirm_visual_location_bootstrap(
    project_id: str,
    location_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.location_bootstrap import confirm_location_bootstrap

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return confirm_location_bootstrap(vpaths, location_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/projects/{project_id}/visual/locations/{location_id}/bootstrap/skip")
def skip_visual_location_bootstrap(
    project_id: str,
    location_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.location_bootstrap import skip_location_bootstrap

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return skip_location_bootstrap(vpaths, location_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/visual/locations/{location_id}/bootstrap/swap-look-lock"
)
def swap_visual_location_bootstrap_look_lock(
    project_id: str,
    location_id: str,
    body: BootstrapSwapBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    from aivp.visual.location_bootstrap import swap_location_look_lock

    vpaths = VisualPaths(settings.data_root, project_id)
    try:
        return swap_location_look_lock(
            vpaths,
            location_id,
            filename=body.filename,
            folder=body.folder,
            denoise=body.denoise,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


_LOCATION_FOLDERS = frozenset(
    {
        "candidates",
        "curated",
        "generations",
        "lora",
        "sheets",
        "look_lock",
        "look_lock_archive",
    }
)


@router.get(
    "/projects/{project_id}/visual/locations/{location_id}/files/{folder}/{filename}"
)
def get_visual_location_file(
    project_id: str,
    location_id: str,
    folder: str,
    filename: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_project(db, project_id)
    if folder not in _LOCATION_FOLDERS:
        raise HTTPException(status_code=400, detail="invalid folder")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    vpaths = VisualPaths(settings.data_root, project_id)
    path = vpaths.location_dir(location_id) / folder / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    headers = None
    if folder == "look_lock":
        headers = {"Cache-Control": "no-store, max-age=0"}
    return FileResponse(path, headers=headers)


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

