from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.candidates import generate_candidates_for_character
from aivp.visual.image_backend import ImageBackend
from aivp.visual.judge import VisionJudge, judge_image
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, load_major_characters
from aivp.visual.qa_tuning import load_qa_tuning, save_qa_tuning
from aivp.visual.sheets import generate_character_sheets

DEFAULT_PASS_RATE = 0.60
DEFAULT_MAX_ROUNDS = 3


def load_project_bible(data_root, project_id: str) -> dict:
    from aivp.bible.overlay import merge_bible
    from aivp.paths import ProjectPaths

    paths = ProjectPaths(data_root, project_id)
    auto: dict = {}
    overlay: dict = {}
    if paths.auto_bible_json.exists():
        auto = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
    if paths.overlay_json.exists():
        overlay = json.loads(paths.overlay_json.read_text(encoding="utf-8"))
    return merge_bible(auto, overlay)


def resolve_major_characters(
    vpaths: VisualPaths,
    *,
    bible: dict | None = None,
    character_ids: list[str] | None = None,
) -> list[dict]:
    doc = bible if isinstance(bible, dict) else load_project_bible(vpaths.data_root, vpaths.project_id)
    majors = load_major_characters(doc)
    if character_ids:
        wanted = set(character_ids)
        majors = [c for c in majors if str(c.get("id") or "") in wanted]
    return majors


def suggest_patches(failure_tags: Counter[str], *, pass_rate: float) -> dict[str, Any]:
    """Map frequent judge failures to generation tuning knobs."""
    patches: dict[str, Any] = {
        "reason_tags": dict(failure_tags.most_common(12)),
        "pass_rate_before": pass_rate,
    }
    total = sum(failure_tags.values()) or 1

    def freq(*keys: str) -> float:
        return sum(failure_tags.get(k, 0) for k in keys) / total

    # Outfit / modesty failures → lower denoise, stronger outfit lock flag.
    if freq("shirtless", "shirtless_or_revealing", "wrong_outfit", "revealing") >= 0.25:
        patches["candidate_denoise_hi"] = 0.68
        patches["candidate_denoise_lo"] = 0.52
        patches["outfit_lock_boost"] = True
        patches["extra_negative"] = (
            "shirtless, bare chest, topless, nude, open shirt, exposed midriff, "
            "wrong outfit, modern clothes, armor"
        )

    # Side/back still front → raise sheet denoise/cfg.
    if freq("wrong_view_front", "wrong_view", "bad_framing") >= 0.20:
        patches["side_denoise"] = 0.94
        patches["back_denoise"] = 0.95
        patches["side_back_cfg"] = 10.0

    # Expression still full body.
    if freq("full_body_instead_of_face", "bad_framing") >= 0.20:
        patches["expr_force_face_crop"] = True
        patches["expr_denoise"] = 0.58

    if not any(
        k in patches
        for k in (
            "candidate_denoise_hi",
            "side_denoise",
            "expr_force_face_crop",
            "outfit_lock_boost",
        )
    ):
        # Generic mild tighten.
        patches["candidate_denoise_hi"] = 0.72
        patches["outfit_lock_boost"] = True
    return patches


def apply_suggested_patches(vpaths: VisualPaths, patches: dict[str, Any]) -> dict[str, Any]:
    current = load_qa_tuning(vpaths)
    history = list(current.get("history") or [])
    history.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "patches": {k: v for k, v in patches.items() if k != "reason_tags"},
            "reason_tags": patches.get("reason_tags"),
            "pass_rate_before": patches.get("pass_rate_before"),
        }
    )
    merged = {**current, **{k: v for k, v in patches.items() if k not in {"reason_tags", "pass_rate_before"}}}
    merged["history"] = history[-20:]
    save_qa_tuning(vpaths, merged)
    return merged


def _infer_slot_from_name(name: str) -> str | None:
    n = name.lower()
    for key in (
        "turnaround_front",
        "turnaround_side",
        "turnaround_back",
        "expr_calm",
        "expr_smile",
        "expr_happy",
        "expr_confused",
        "expr_angry",
        "expr_sad",
        "expr_surprised",
        "expr_shy",
    ):
        if key in n:
            return key
    if n.startswith("cand_") or "_cand" in n or "cand" in n:
        return None
    return None


def evaluate_character_images(
    vpaths: VisualPaths,
    character: dict,
    vision: VisionJudge,
    *,
    include_candidates: bool = True,
    include_sheets: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    profile = ensure_profile(vpaths, character)
    cid = profile["character_id"]
    items: list[tuple[Path, str | None, str]] = []
    if include_candidates:
        for p in sorted(vpaths.candidates_dir(cid).glob("*.png"), key=lambda x: x.name):
            items.append((p, None, "candidate"))
    if include_sheets:
        for p in sorted(vpaths.sheets_dir(cid).glob("*.png"), key=lambda x: x.name):
            slot = _infer_slot_from_name(p.name)
            kind = "expression" if (slot or "").startswith("expr_") else "turnaround"
            if slot is None:
                # Prefer meta.json
                meta = p.with_suffix(".meta.json")
                if meta.exists():
                    try:
                        payload = json.loads(meta.read_text(encoding="utf-8"))
                        slot = str(payload.get("key") or "") or None
                        kind = "expression" if (slot or "").startswith("expr_") else "turnaround"
                    except (OSError, json.JSONDecodeError):
                        pass
            items.append((p, slot, kind))
    if limit is not None:
        items = items[: max(0, int(limit))]

    results: list[dict[str, Any]] = []
    tags: Counter[str] = Counter()
    by_kind: dict[str, list[bool]] = {"candidate": [], "turnaround": [], "expression": []}
    for path, slot, kind in items:
        judged = judge_image(vision, profile, path, slot_key=slot)
        judged["kind"] = kind
        results.append(judged)
        for t in judged.get("failure_tags") or []:
            tags[str(t)] += 1
        by_kind.setdefault(kind, []).append(bool(judged.get("pass")))

    def rate(vals: list[bool]) -> float | None:
        if not vals:
            return None
        return sum(1 for v in vals if v) / len(vals)

    overall = [bool(r.get("pass")) for r in results]
    report = {
        "character_id": cid,
        "name": profile.get("name"),
        "count": len(results),
        "pass_count": sum(1 for v in overall if v),
        "pass_rate": rate(overall),
        "pass_rate_by_kind": {k: rate(v) for k, v in by_kind.items()},
        "failure_tags": dict(tags.most_common()),
        "results": results,
    }
    return report


def run_self_check_round(
    vpaths: VisualPaths,
    character: dict,
    backend: ImageBackend,
    vision: VisionJudge,
    *,
    candidate_count: int = 4,
    sheet_group: str = "all",
    regenerate: bool = True,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Optionally regenerate then judge; return report + suggested patches if failing."""
    if regenerate:
        generate_candidates_for_character(
            vpaths,
            character,
            backend,
            count=candidate_count,
            should_cancel=should_cancel,
        )
        generate_character_sheets(
            vpaths,
            character,
            backend,
            group=sheet_group,
            should_cancel=should_cancel,
        )
    # Judge only newest batch: last N candidates + all current sheets is heavy;
    # evaluate everything but cap candidates to latest batch via limit on candidates folder order.
    report = evaluate_character_images(
        vpaths,
        character,
        vision,
        include_candidates=True,
        include_sheets=True,
        limit=None,
    )
    # Focus metrics on latest candidates (last candidate_count) + sheets.
    cid = report["character_id"]
    cand_files = sorted(vpaths.candidates_dir(cid).glob("*.png"), key=lambda x: x.name)
    latest = set(p.name for p in cand_files[-max(1, candidate_count) :])
    focused = [
        r
        for r in report["results"]
        if r.get("kind") != "candidate" or r.get("image") in latest
    ]
    tags: Counter[str] = Counter()
    for r in focused:
        for t in r.get("failure_tags") or []:
            tags[str(t)] += 1
    passes = [bool(r.get("pass")) for r in focused]
    pass_rate = (sum(1 for v in passes if v) / len(passes)) if passes else 0.0
    report["focused_count"] = len(focused)
    report["focused_pass_rate"] = pass_rate
    report["focused_failure_tags"] = dict(tags.most_common())
    patches = suggest_patches(tags, pass_rate=pass_rate)
    report["suggested_patches"] = patches
    return report


def run_self_check_loop(
    vpaths: VisualPaths,
    backend: ImageBackend,
    vision: VisionJudge,
    *,
    bible: dict | None = None,
    character_ids: list[str] | None = None,
    pass_rate_threshold: float = DEFAULT_PASS_RATE,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    candidate_count: int = 4,
    apply_patches: bool = True,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    majors = resolve_major_characters(
        vpaths, bible=bible, character_ids=character_ids
    )
    if not majors:
        raise ValueError("no_major_characters_for_self_check")

    rounds: list[dict[str, Any]] = []
    for round_i in range(1, max_rounds + 1):
        if should_cancel and should_cancel():
            break
        round_reports: list[dict[str, Any]] = []
        all_tags: Counter[str] = Counter()
        focused_pass = 0
        focused_total = 0
        for ch in majors:
            rep = run_self_check_round(
                vpaths,
                ch,
                backend,
                vision,
                candidate_count=candidate_count,
                regenerate=True,
                should_cancel=should_cancel,
            )
            round_reports.append(
                {
                    "character_id": rep["character_id"],
                    "name": rep.get("name"),
                    "focused_pass_rate": rep.get("focused_pass_rate"),
                    "focused_count": rep.get("focused_count"),
                    "failure_tags": rep.get("focused_failure_tags"),
                    "suggested_patches": rep.get("suggested_patches"),
                }
            )
            focused_pass += int(round(float(rep.get("focused_pass_rate") or 0) * int(rep.get("focused_count") or 0)))
            focused_total += int(rep.get("focused_count") or 0)
            for k, v in (rep.get("focused_failure_tags") or {}).items():
                all_tags[str(k)] += int(v)

        rate = (focused_pass / focused_total) if focused_total else 0.0
        patches = suggest_patches(all_tags, pass_rate=rate)
        applied = None
        if apply_patches and rate < pass_rate_threshold:
            applied = apply_suggested_patches(vpaths, patches)
        entry = {
            "round": round_i,
            "pass_rate": rate,
            "threshold": pass_rate_threshold,
            "passed": rate >= pass_rate_threshold,
            "characters": round_reports,
            "patches": patches,
            "applied_tuning": applied,
        }
        rounds.append(entry)
        if rate >= pass_rate_threshold:
            break

    summary = {
        "project_visual_root": str(vpaths.root),
        "character_ids": [str(c.get("id")) for c in majors],
        "pass_rate_threshold": pass_rate_threshold,
        "rounds": rounds,
        "final_pass_rate": rounds[-1]["pass_rate"] if rounds else 0.0,
        "final_passed": bool(rounds and rounds[-1]["passed"]),
        "tuning": load_qa_tuning(vpaths),
    }
    out = vpaths.root / "qa_self_check_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["report_path"] = str(out)
    return summary
