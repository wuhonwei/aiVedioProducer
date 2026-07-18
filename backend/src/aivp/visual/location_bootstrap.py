"""Auto location trainset bootstrap: description QA → establishing lock → expand → confirm."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aivp.visual.location_bootstrap_tuning import (
    apply_location_failure_tags,
    load_location_bootstrap_tuning,
)
from aivp.visual.location_candidates import generate_location_candidates_for
from aivp.visual.location_curate import curate_location_images
from aivp.visual.location_description_qa import qa_location_description
from aivp.visual.location_judge import is_location_look_lock_eligible, judge_location_image
from aivp.visual.location_look_lock import set_location_look_lock
from aivp.visual.location_profiles import (
    ensure_location_profile,
    load_major_locations,
    read_location_profile,
    save_location_profile,
)
from aivp.visual.location_sheets import generate_location_sheets
from aivp.visual.paths import VisualPaths

ProgressCb = Callable[[dict[str, Any]], None]


def _emit(on_progress: ProgressCb | None, **payload: Any) -> None:
    if on_progress:
        on_progress(payload)


def _load_entity_map(entities_json: Path) -> dict[str, dict]:
    if not entities_json.exists():
        return {}
    data = json.loads(entities_json.read_text(encoding="utf-8"))
    locs = data.get("locations") if isinstance(data, dict) else []
    out: dict[str, dict] = {}
    for ent in locs or []:
        if isinstance(ent, dict) and ent.get("id"):
            out[str(ent["id"])] = ent
            if ent.get("name"):
                out[str(ent["name"])] = ent
    return out


def _delete_png_and_sidecar(path: Path) -> None:
    for p in (path, path.with_suffix(".txt"), path.with_suffix(".json")):
        if p.exists():
            p.unlink()


def _archive_top(
    vpaths: VisualPaths,
    location_id: str,
    ranked: list[tuple[str, float]],
    *,
    top_k: int,
) -> list[str]:
    archive = vpaths.location_dir(location_id) / "look_lock_archive"
    if archive.exists():
        for old in archive.glob("*"):
            if old.is_file():
                old.unlink()
    archive.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    cand_dir = vpaths.location_candidates_dir(location_id)
    for name, _score in ranked[: max(0, top_k)]:
        src = cand_dir / name
        if not src.exists():
            continue
        shutil.copy2(src, archive / name)
        for suf in (".txt", ".json"):
            side = src.with_suffix(suf)
            if side.exists():
                shutil.copy2(side, archive / side.name)
        saved.append(name)
    return saved


def _judge_or_heuristic(
    vision: Any,
    profile: dict,
    image_path: Path,
    *,
    slot_key: str | None = None,
) -> dict[str, Any]:
    if vision is not None:
        return judge_location_image(vision, profile, image_path, slot_key=slot_key)
    return {
        "pass": True,
        "score": 0.75,
        "summary": "heuristic_pass_no_vision",
        "checks": {
            "no_people": {"pass": True, "note": "heuristic"},
            "place_readable": {"pass": True, "note": "heuristic"},
            "establishing_or_env": {"pass": True, "note": "heuristic"},
            "style_match": {"pass": True, "note": "heuristic"},
            "not_character_sheet": {"pass": True, "note": "heuristic"},
        },
        "failure_tags": [],
        "image": image_path.name,
        "slot_key": slot_key,
    }


def bootstrap_location(
    vpaths: VisualPaths,
    location: dict,
    backend: Any,
    *,
    settings: Any,
    vision: Any = None,
    llm: Any = None,
    entity: dict | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    profile = ensure_location_profile(vpaths, location)
    lid = profile["location_id"]
    warnings: list[str] = []
    lock_count = int(getattr(settings, "location_bootstrap_lock_count", 14) or 14)
    lock_count = max(10, min(20, lock_count))
    lock_retries = int(getattr(settings, "location_bootstrap_lock_batch_retries", 3) or 3)
    slot_retries = int(getattr(settings, "location_bootstrap_slot_retries", 3) or 3)
    desc_retries = int(getattr(settings, "location_bootstrap_desc_rewrite_retries", 3) or 3)
    archive_k = int(getattr(settings, "location_bootstrap_archive_top_k", 3) or 3)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    _emit(on_progress, location_id=lid, step="description_qa", message="校验地点描述")
    qa = qa_location_description(
        profile, entity, llm=llm, max_rewrites=desc_retries
    )
    profile = qa["profile"]
    warnings.extend(qa.get("warnings") or [])
    save_location_profile(vpaths, profile)
    if not qa.get("ok"):
        profile["bootstrap_status"] = "description_needs_review"
        save_location_profile(vpaths, profile)
        return {
            "location_id": lid,
            "status": "description_needs_review",
            "warnings": warnings,
        }

    winner: str | None = None
    ranked: list[tuple[str, float]] = []
    for batch_i in range(max(1, lock_retries)):
        if cancelled():
            return {"location_id": lid, "status": "cancelled", "warnings": warnings}
        _emit(
            on_progress,
            location_id=lid,
            step="lock_candidates",
            message=f"生成建立镜头候选 batch {batch_i + 1}/{lock_retries}",
            batch=batch_i + 1,
        )
        for old in vpaths.location_candidates_dir(lid).glob("*.png"):
            _delete_png_and_sidecar(old)
        gen = generate_location_candidates_for(
            vpaths,
            location,
            backend,
            count=lock_count,
            should_cancel=should_cancel,
        )
        tag_counter: Counter[str] = Counter()
        ranked = []
        for name in gen.get("files") or []:
            if cancelled():
                break
            path = vpaths.location_candidates_dir(lid) / name
            judged = _judge_or_heuristic(vision, profile, path, slot_key="candidate")
            for t in judged.get("failure_tags") or []:
                tag_counter[str(t)] += 1
            if is_location_look_lock_eligible(judged):
                ranked.append((name, float(judged.get("score") or 0)))
        ranked.sort(key=lambda x: x[1], reverse=True)
        if ranked:
            winner = ranked[0][0]
            break
        if tag_counter:
            apply_location_failure_tags(vpaths, lid, tag_counter)
            warnings.append(f"lock_batch_{batch_i + 1}_retuned:{dict(tag_counter)}")

    if not winner:
        profile["bootstrap_status"] = "look_lock_needs_review"
        save_location_profile(vpaths, profile)
        warnings.append("look_lock_needs_review")
        return {
            "location_id": lid,
            "status": "look_lock_needs_review",
            "warnings": warnings,
            "tuning": load_location_bootstrap_tuning(vpaths, lid),
        }

    _emit(on_progress, location_id=lid, step="set_look_lock", message=f"定妆 {winner}")
    archived = _archive_top(vpaths, lid, ranked, top_k=archive_k)
    set_location_look_lock(
        vpaths, lid, folder="candidates", filename=winner, denoise=0.55
    )
    keep_names = set(archived) | {winner}
    for old in list(vpaths.location_candidates_dir(lid).glob("*.png")):
        if old.name not in keep_names:
            _delete_png_and_sidecar(old)

    profile = ensure_location_profile(vpaths, location)
    profile["bootstrap_status"] = "expanding"
    profile["bootstrap_lock_file"] = winner
    profile["bootstrap_archive"] = archived
    save_location_profile(vpaths, profile)

    _emit(on_progress, location_id=lid, step="expand_candidates", message="定妆后多角度空镜")
    expand_n = min(8, lock_count)
    kept_cands: list[str] = []
    for _attempt in range(max(1, slot_retries)):
        if cancelled():
            break
        out = generate_location_candidates_for(
            vpaths, location, backend, count=expand_n, should_cancel=should_cancel
        )
        tag_counter = Counter()
        for name in out.get("files") or []:
            path = vpaths.location_candidates_dir(lid) / name
            judged = _judge_or_heuristic(vision, profile, path, slot_key="candidate")
            if judged.get("pass"):
                kept_cands.append(name)
            else:
                for t in judged.get("failure_tags") or []:
                    tag_counter[str(t)] += 1
                _delete_png_and_sidecar(path)
        if kept_cands:
            break
        if tag_counter:
            apply_location_failure_tags(vpaths, lid, tag_counter)

    _emit(on_progress, location_id=lid, step="expand_sheets", message="时段与材质空镜")
    sheet_keys = [
        "establishing_wide",
        "angle_three_quarter",
        "tod_dawn",
        "tod_dusk",
        "weather_fog",
        "material_stone",
    ]
    kept_sheets: list[str] = []
    for _attempt in range(max(1, slot_retries)):
        if cancelled():
            break
        sheets = generate_location_sheets(
            vpaths,
            location,
            backend,
            slot_keys=sheet_keys,
            should_cancel=should_cancel,
        )
        tag_counter = Counter()
        for item in sheets.get("files") or []:
            name = item.get("file") if isinstance(item, dict) else None
            key = item.get("key") if isinstance(item, dict) else None
            if not name:
                continue
            path = vpaths.location_sheets_dir(lid) / name
            judged = _judge_or_heuristic(vision, profile, path, slot_key=key)
            if judged.get("pass"):
                kept_sheets.append(name)
            else:
                for t in judged.get("failure_tags") or []:
                    tag_counter[str(t)] += 1
                _delete_png_and_sidecar(path)
        if kept_sheets:
            break
        if tag_counter:
            apply_location_failure_tags(vpaths, lid, tag_counter)

    _emit(on_progress, location_id=lid, step="package", message="写入地点训练集")
    keep = [n for n in kept_cands if (vpaths.location_candidates_dir(lid) / n).exists()]
    if winner and (vpaths.location_candidates_dir(lid) / winner).exists() and winner not in keep:
        keep.append(winner)
    keep_sheets = [n for n in kept_sheets if (vpaths.location_sheets_dir(lid) / n).exists()]
    if keep or keep_sheets:
        curate_location_images(vpaths, lid, keep, keep_sheets=keep_sheets)
    profile = ensure_location_profile(vpaths, location)
    profile["bootstrap_status"] = "awaiting_confirm"
    profile["train_status"] = "awaiting_confirm"
    profile["bootstrap_warnings"] = warnings
    save_location_profile(vpaths, profile)
    _emit(on_progress, location_id=lid, step="awaiting_confirm", message="待人工确认")
    return {
        "location_id": lid,
        "status": "awaiting_confirm",
        "look_lock_file": winner,
        "archive": archived,
        "curated_candidates": keep,
        "curated_sheets": keep_sheets,
        "warnings": warnings,
    }


def bootstrap_locations_project(
    vpaths: VisualPaths,
    bible: dict,
    backend: Any,
    *,
    settings: Any,
    vision: Any = None,
    llm: Any = None,
    entities_json: Path | None = None,
    location_ids: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    majors = load_major_locations(bible)
    if location_ids:
        want = set(location_ids)
        majors = [c for c in majors if c.get("id") in want]
    entity_map = _load_entity_map(entities_json) if entities_json else {}
    results = []
    total = max(len(majors), 1)
    for i, loc in enumerate(majors, start=1):
        if should_cancel and should_cancel():
            break
        lid = str(loc.get("id") or "")
        entity = entity_map.get(lid) or entity_map.get(str(loc.get("name") or ""))
        _emit(
            on_progress,
            location_id=lid,
            step="start",
            message=f"开始 {loc.get('name') or lid}",
            done=i - 1,
            total=total,
        )

        def _loc_progress(payload: dict[str, Any]) -> None:
            payload = dict(payload)
            payload.setdefault("done", i - 1)
            payload.setdefault("total", total)
            _emit(on_progress, **payload)

        results.append(
            bootstrap_location(
                vpaths,
                loc,
                backend,
                settings=settings,
                vision=vision,
                llm=llm,
                entity=entity,
                should_cancel=should_cancel,
                on_progress=_loc_progress,
            )
        )
        _emit(
            on_progress,
            location_id=lid,
            step="done",
            message=f"完成 {loc.get('name') or lid}",
            done=i,
            total=total,
        )
    return {"locations": results, "count": len(results)}


def confirm_location_bootstrap(vpaths: VisualPaths, location_id: str) -> dict[str, Any]:
    path = vpaths.location_profile_json(location_id)
    profile = read_location_profile(path)
    if not profile:
        raise FileNotFoundError(f"profile_missing:{location_id}")
    profile["bootstrap_status"] = "confirmed"
    profile["train_status"] = "curated_ready"
    save_location_profile(vpaths, profile)
    return {
        "location_id": location_id,
        "bootstrap_status": "confirmed",
        "train_status": "curated_ready",
    }


def skip_location_bootstrap(vpaths: VisualPaths, location_id: str) -> dict[str, Any]:
    path = vpaths.location_profile_json(location_id)
    profile = read_location_profile(path)
    if not profile:
        raise FileNotFoundError(f"profile_missing:{location_id}")
    profile["bootstrap_status"] = "skipped"
    save_location_profile(vpaths, profile)
    return {"location_id": location_id, "bootstrap_status": "skipped"}


def swap_location_look_lock(
    vpaths: VisualPaths,
    location_id: str,
    *,
    filename: str,
    folder: str = "look_lock_archive",
    denoise: float | None = None,
) -> dict[str, Any]:
    if folder not in {"look_lock_archive", "candidates", "curated", "sheets"}:
        raise ValueError(f"invalid_swap_folder:{folder}")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid_filename")
    src = vpaths.location_dir(location_id) / folder / filename
    if not src.exists():
        raise FileNotFoundError(f"swap_source_missing:{folder}/{filename}")
    profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
    lock_denoise = float(denoise) if denoise is not None else float(
        (profile.get("look_lock") or {}).get("denoise") or 0.55
    )
    result = set_location_look_lock(
        vpaths,
        location_id,
        folder=folder,
        filename=filename,
        denoise=lock_denoise,
    )
    profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
    profile["bootstrap_status"] = "awaiting_confirm"
    profile["train_status"] = "awaiting_confirm"
    profile["bootstrap_lock_file"] = filename
    save_location_profile(vpaths, profile)
    return {
        "location_id": location_id,
        "look_lock": result.get("look_lock"),
        "bootstrap_status": "awaiting_confirm",
        "swapped_from": {"folder": folder, "file": filename},
    }
