"""Auto trainset bootstrap: description QA → look-lock → expand → await confirm."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aivp.visual.bootstrap_tuning import (
    apply_failure_tags,
    load_bootstrap_tuning,
)
from aivp.visual.candidates import generate_candidates_for_character
from aivp.visual.curate import curate_candidates
from aivp.visual.description_qa import qa_character_description
from aivp.visual.judge import is_look_lock_eligible, judge_image
from aivp.visual.look_lock import set_look_lock
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import (
    ensure_profile,
    load_major_characters,
    read_profile_json,
    save_profile,
)
from aivp.visual.sheets import generate_character_sheets


ProgressCb = Callable[[dict[str, Any]], None]


def _emit(on_progress: ProgressCb | None, **payload: Any) -> None:
    if on_progress:
        on_progress(payload)


def _load_entity_map(entities_json: Path) -> dict[str, dict]:
    if not entities_json.exists():
        return {}
    data = json.loads(entities_json.read_text(encoding="utf-8"))
    chars = data.get("characters") if isinstance(data, dict) else []
    out: dict[str, dict] = {}
    for ent in chars or []:
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
    character_id: str,
    ranked: list[tuple[str, float]],
    *,
    top_k: int,
) -> list[str]:
    archive = vpaths.character_dir(character_id) / "look_lock_archive"
    if archive.exists():
        for old in archive.glob("*"):
            if old.is_file():
                old.unlink()
    archive.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    cand_dir = vpaths.candidates_dir(character_id)
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
        return judge_image(vision, profile, image_path, slot_key=slot_key)
    # Stub path: assume full-body lock-eligible so unit tests can run offline.
    return {
        "pass": True,
        "score": 0.75,
        "summary": "heuristic_pass_no_vision",
        "checks": {
            "framing": {"pass": True, "note": "heuristic"},
            "clothing_covered": {"pass": True, "note": "heuristic"},
            "outfit_complete": {"pass": True, "note": "heuristic"},
            "background_plain": {"pass": True, "note": "heuristic"},
            "gender": {"pass": True, "note": "heuristic"},
            "age": {"pass": True, "note": "heuristic"},
        },
        "failure_tags": [],
        "image": image_path.name,
        "slot_key": slot_key,
    }


def bootstrap_character(
    vpaths: VisualPaths,
    character: dict,
    backend: Any,
    *,
    settings: Any,
    vision: Any = None,
    llm: Any = None,
    entity: dict | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    profile = ensure_profile(vpaths, character)
    cid = profile["character_id"]
    warnings: list[str] = []
    lock_count = int(getattr(settings, "bootstrap_lock_candidate_count", 14) or 14)
    lock_count = max(10, min(20, lock_count))
    lock_retries = int(getattr(settings, "bootstrap_lock_batch_retries", 3) or 3)
    slot_retries = int(getattr(settings, "bootstrap_slot_retries", 3) or 3)
    desc_retries = int(getattr(settings, "bootstrap_desc_rewrite_retries", 3) or 3)
    archive_k = int(getattr(settings, "bootstrap_archive_top_k", 3) or 3)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    # --- A. Description QA ---
    _emit(on_progress, character_id=cid, step="description_qa", message="校验角色描述")
    qa = qa_character_description(
        profile, entity, llm=llm, max_rewrites=desc_retries
    )
    profile = qa["profile"]
    warnings.extend(qa.get("warnings") or [])
    save_profile(vpaths, profile)
    if not qa.get("ok"):
        profile["bootstrap_status"] = "description_needs_review"
        save_profile(vpaths, profile)
        return {
            "character_id": cid,
            "status": "description_needs_review",
            "warnings": warnings,
        }

    # --- B/C. Look-lock batches ---
    winner: str | None = None
    ranked: list[tuple[str, float]] = []
    for batch_i in range(max(1, lock_retries)):
        if cancelled():
            return {"character_id": cid, "status": "cancelled", "warnings": warnings}
        _emit(
            on_progress,
            character_id=cid,
            step="lock_candidates",
            message=f"生成定妆候选 batch {batch_i + 1}/{lock_retries}",
            batch=batch_i + 1,
        )
        # Clear previous candidates for a clean lock batch.
        for old in vpaths.candidates_dir(cid).glob("*.png"):
            _delete_png_and_sidecar(old)
        gen = generate_candidates_for_character(
            vpaths,
            character,
            backend,
            count=lock_count,
            should_cancel=should_cancel,
        )
        tag_counter: Counter[str] = Counter()
        ranked = []
        for name in gen.get("files") or []:
            if cancelled():
                break
            path = vpaths.candidates_dir(cid) / name
            judged = _judge_or_heuristic(vision, profile, path, slot_key="candidate")
            for t in judged.get("failure_tags") or []:
                tag_counter[str(t)] += 1
            if is_look_lock_eligible(judged):
                ranked.append((name, float(judged.get("score") or 0)))
        ranked.sort(key=lambda x: x[1], reverse=True)
        if ranked:
            winner = ranked[0][0]
            break
        if tag_counter:
            apply_failure_tags(vpaths, cid, tag_counter)
            warnings.append(f"lock_batch_{batch_i + 1}_retuned:{dict(tag_counter)}")

    if not winner:
        # Best-effort: keep highest-scoring image even if not eligible.
        profile["bootstrap_status"] = "look_lock_needs_review"
        save_profile(vpaths, profile)
        warnings.append("look_lock_needs_review")
        return {
            "character_id": cid,
            "status": "look_lock_needs_review",
            "warnings": warnings,
            "tuning": load_bootstrap_tuning(vpaths, cid),
        }

    # --- D. Set look-lock + archive ---
    _emit(on_progress, character_id=cid, step="set_look_lock", message=f"定妆 {winner}")
    archived = _archive_top(vpaths, cid, ranked, top_k=archive_k)
    set_look_lock(vpaths, cid, folder="candidates", filename=winner, denoise=0.55)
    # Delete non-archived lock-batch candidates (winner stays until expand regenerates).
    keep_names = set(archived) | {winner}
    for old in list(vpaths.candidates_dir(cid).glob("*.png")):
        if old.name not in keep_names:
            _delete_png_and_sidecar(old)

    profile = ensure_profile(vpaths, character)
    profile["bootstrap_status"] = "expanding"
    profile["bootstrap_lock_file"] = winner
    profile["bootstrap_archive"] = archived
    save_profile(vpaths, profile)

    # --- E. Expand: locked candidates + sheets ---
    _emit(on_progress, character_id=cid, step="expand_candidates", message="定妆后多姿态候选")
    for old in vpaths.candidates_dir(cid).glob("*.png"):
        if old.name != winner and old.name not in archived:
            _delete_png_and_sidecar(old)
    # Generate pose variants under look-lock (plain bg via existing prompts).
    expand_n = min(8, lock_count)
    kept_cands: list[str] = []
    for attempt in range(max(1, slot_retries)):
        if cancelled():
            break
        out = generate_candidates_for_character(
            vpaths, character, backend, count=expand_n, should_cancel=should_cancel
        )
        tag_counter = Counter()
        for name in out.get("files") or []:
            path = vpaths.candidates_dir(cid) / name
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
            apply_failure_tags(vpaths, cid, tag_counter)

    _emit(on_progress, character_id=cid, step="expand_sheets", message="三视与表情")
    sheet_keys = [
        "turnaround_front",
        "turnaround_side",
        "turnaround_back",
        "expr_calm",
        "expr_smile",
        "expr_sad",
        "expr_angry",
    ]
    kept_sheets: list[str] = []
    for attempt in range(max(1, slot_retries)):
        if cancelled():
            break
        sheets = generate_character_sheets(
            vpaths,
            character,
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
            path = vpaths.sheets_dir(cid) / name
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
            apply_failure_tags(vpaths, cid, tag_counter)

    # --- F. Package curated ---
    _emit(on_progress, character_id=cid, step="package", message="写入训练集")
    # Prefer expanded keepers; include winner if still present.
    keep = [n for n in kept_cands if (vpaths.candidates_dir(cid) / n).exists()]
    if winner and (vpaths.candidates_dir(cid) / winner).exists() and winner not in keep:
        keep.append(winner)
    keep_sheets = [n for n in kept_sheets if (vpaths.sheets_dir(cid) / n).exists()]
    if keep or keep_sheets:
        curate_candidates(vpaths, cid, keep, keep_sheets=keep_sheets)
    profile = ensure_profile(vpaths, character)
    profile["bootstrap_status"] = "awaiting_confirm"
    profile["train_status"] = "awaiting_confirm"
    profile["bootstrap_warnings"] = warnings
    save_profile(vpaths, profile)
    _emit(on_progress, character_id=cid, step="awaiting_confirm", message="待人工确认")
    return {
        "character_id": cid,
        "status": "awaiting_confirm",
        "look_lock_file": winner,
        "archive": archived,
        "curated_candidates": keep,
        "curated_sheets": keep_sheets,
        "warnings": warnings,
    }


def bootstrap_project(
    vpaths: VisualPaths,
    bible: dict,
    backend: Any,
    *,
    settings: Any,
    vision: Any = None,
    llm: Any = None,
    entities_json: Path | None = None,
    character_ids: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    majors = load_major_characters(bible)
    if character_ids:
        want = set(character_ids)
        majors = [c for c in majors if c.get("id") in want]
    entity_map = _load_entity_map(entities_json) if entities_json else {}
    results = []
    total = max(len(majors), 1)
    for i, ch in enumerate(majors, start=1):
        if should_cancel and should_cancel():
            break
        cid = str(ch.get("id") or "")
        entity = entity_map.get(cid) or entity_map.get(str(ch.get("name") or ""))
        _emit(
            on_progress,
            character_id=cid,
            step="start",
            message=f"开始 {ch.get('name') or cid}",
            done=i - 1,
            total=total,
        )

        def _char_progress(payload: dict[str, Any]) -> None:
            payload = dict(payload)
            payload.setdefault("done", i - 1)
            payload.setdefault("total", total)
            _emit(on_progress, **payload)

        results.append(
            bootstrap_character(
                vpaths,
                ch,
                backend,
                settings=settings,
                vision=vision,
                llm=llm,
                entity=entity,
                should_cancel=should_cancel,
                on_progress=_char_progress,
            )
        )
        _emit(
            on_progress,
            character_id=cid,
            step="done",
            message=f"完成 {ch.get('name') or cid}",
            done=i,
            total=total,
        )
    return {"characters": results, "count": len(results)}


def confirm_bootstrap(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    """Human confirms trainset; ready for package / LoRA (still no auto-train)."""
    path = vpaths.profile_json(character_id)
    profile = read_profile_json(path)
    if not profile:
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile["bootstrap_status"] = "confirmed"
    profile["train_status"] = "curated_ready"
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "bootstrap_status": "confirmed",
        "train_status": "curated_ready",
    }


def skip_bootstrap(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    path = vpaths.profile_json(character_id)
    profile = read_profile_json(path)
    if not profile:
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile["bootstrap_status"] = "skipped"
    save_profile(vpaths, profile)
    return {"character_id": character_id, "bootstrap_status": "skipped"}


def swap_look_lock(
    vpaths: VisualPaths,
    character_id: str,
    *,
    filename: str,
    folder: str = "look_lock_archive",
    denoise: float | None = None,
) -> dict[str, Any]:
    """Swap look-lock to an archived (or candidate) image for human review."""
    if folder not in {"look_lock_archive", "candidates", "curated", "sheets"}:
        raise ValueError(f"invalid_swap_folder:{folder}")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid_filename")
    src_dir = vpaths.character_dir(character_id) / folder
    src = src_dir / filename
    if not src.exists():
        raise FileNotFoundError(f"swap_source_missing:{folder}/{filename}")
    profile = read_profile_json(vpaths.profile_json(character_id)) or {}
    lock_denoise = float(denoise) if denoise is not None else float(
        (profile.get("look_lock") or {}).get("denoise") or 0.55
    )
    result = set_look_lock(
        vpaths,
        character_id,
        folder=folder,
        filename=filename,
        denoise=lock_denoise,
    )
    profile = read_profile_json(vpaths.profile_json(character_id)) or {}
    profile["bootstrap_status"] = "awaiting_confirm"
    profile["train_status"] = "awaiting_confirm"
    profile["bootstrap_lock_file"] = filename
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "look_lock": result.get("look_lock"),
        "bootstrap_status": "awaiting_confirm",
        "swapped_from": {"folder": folder, "file": filename},
    }
