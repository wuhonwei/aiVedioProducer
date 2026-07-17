from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.look_lock import candidate_cfg_for, candidate_denoise_for, resolve_look_lock
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, load_major_characters
from aivp.visual.prompts import build_candidate_prompt, candidate_negative_for
from aivp.visual.qa_tuning import load_qa_tuning


VIEW_PROMPTS = [
    "solo, 1person, full body, head to toe, feet visible, facing camera, standing, plain background",
    "solo, 1person, full body, head to toe, feet visible, three quarter view, standing, plain background",
    "solo, 1person, full body, head to toe, feet visible, side profile standing, plain background",
    "solo, 1person, full body, head to toe, feet visible, looking away, standing, soft light, plain background",
    "solo, 1person, full body, head to toe, feet visible, slight contrapposto standing pose, plain background",
    "solo, 1person, full body, head to toe, feet visible, walking pose, plain background",
    "solo, 1person, full body, head to toe, feet visible, standing hands at sides, plain background",
    "solo, 1person, full body, head to toe, feet visible, standing relaxed pose, plain background",
]

# When look-lock is on: keep face/outfit fixed; vary action and mild camera turn.
LOOK_LOCK_ACTION_PROMPTS = [
    "full body, head to toe, feet visible, facing camera, standing neutral, arms relaxed at sides, plain background",
    "full body, head to toe, feet visible, three quarter view, waving one hand greeting pose, plain background",
    "full body, head to toe, feet visible, facing camera, walking forward mid-step, plain background",
    "full body, head to toe, feet visible, slight body turn, respectful bow pose, plain background",
    "full body, head to toe, feet visible, facing camera, hands clasped in front, plain background",
    "full body, head to toe, feet visible, three quarter view, one hand on hip standing pose, plain background",
    "full body, head to toe, feet visible, facing camera, pointing forward with one hand, plain background",
    "full body, head to toe, feet visible, slight three quarter turn, arms crossed standing pose, plain background",
]


def _look_lock_candidate_negative(base_neg: str) -> str:
    extra = (
        "different face, different hairstyle, different hair color, different outfit, "
        "costume change, clothing redesign, wardrobe change, new clothes, "
        "different sleeve length, different collar, different garment color, "
        "recolored clothes, pattern change, accessory change, "
        "shirtless, bare chest, topless, nude, naked, open shirt, exposed midriff, "
        "face morph, identity drift, age change, gender change, "
        "static copy of reference, identical pose as reference, frozen stance"
    )
    return f"{base_neg}, {extra}"



def _unique_stem(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{stamp}"


def generate_candidates_for_character(
    vpaths: VisualPaths,
    character: dict,
    backend: ImageBackend,
    *,
    count: int = 8,
    negative: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    profile = ensure_profile(vpaths, character)
    cid = profile["character_id"]
    out_dir = vpaths.candidates_dir(cid)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    # No hard cap on how many times the user may generate; soft ceiling avoids runaway jobs.
    n = max(1, min(int(count), 100))
    neg = negative or candidate_negative_for(profile)
    ref_image, base_denoise = resolve_look_lock(vpaths, cid, profile)
    tuning = load_qa_tuning(vpaths)
    if ref_image:
        neg = _look_lock_candidate_negative(neg)
    if tuning.get("extra_negative"):
        neg = f"{neg}, {tuning['extra_negative']}"
    batch = _unique_stem("cand")
    # New base each batch so Comfy does not replay the same 8 seeds forever.
    seed_base = fresh_seed()
    if on_progress:
        on_progress(0, n)
    used_denoises: list[float] = []
    for i in range(n):
        if should_cancel and should_cancel():
            break
        if ref_image:
            action = LOOK_LOCK_ACTION_PROMPTS[i % len(LOOK_LOCK_ACTION_PROMPTS)]
            view = f"solo, 1person, {action}"
        else:
            view = VIEW_PROMPTS[i % len(VIEW_PROMPTS)]
        prompt = build_candidate_prompt(profile, view)
        denoise = 1.0
        cfg = 8.0
        if ref_image:
            denoise = candidate_denoise_for(view, base_denoise, index=i, tuning=tuning)
            used_denoises.append(denoise)
            cfg = candidate_cfg_for()
            prompt = (
                f"{prompt}, exact same face hairstyle hair color and outfit as reference, "
                "identical clothing colors seams accessories and fabric, "
                "fully clothed covered chest closed collar, "
                "must change body pose gesture and stance clearly, "
                "do not redesign wardrobe or facial features, do not keep the reference pose, "
                "no shirtless no bare chest no revealing clothes"
            )
        if tuning.get("outfit_lock_boost"):
            prompt = (
                f"{prompt}, fully clothed, covered torso, exact wardrobe colors, "
                "guofeng cloak or tunic as described, no bare chest"
            )
        name = f"{batch}_{i+1:03d}.png"
        dest = out_dir / name
        backend.generate(
            prompt=prompt,
            negative=neg,
            dest=dest,
            seed=(seed_base + i) % (2_147_483_647 + 1),
            width=768,
            height=1024,
            ref_image=ref_image,
            denoise=denoise,
            cfg=cfg,
        )
        dest.with_suffix(".txt").write_text(prompt, encoding="utf-8")
        created.append(dest.name)
        if on_progress:
            on_progress(len(created), n)
    profile["status"] = "candidates_ready"
    profile["candidates_generated_at"] = datetime.now(timezone.utc).isoformat()
    if ref_image:
        profile["candidates_used_look_lock"] = True
    vpaths.profile_json(cid).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "character_id": cid,
        "files": created,
        "trigger": profile["trigger"],
        "look_lock": bool(ref_image),
        "denoise": (
            sum(used_denoises) / len(used_denoises) if used_denoises else (base_denoise if ref_image else 1.0)
        ),
    }


def generate_candidates(
    vpaths: VisualPaths,
    bible: dict,
    backend: ImageBackend,
    *,
    character_ids: list[str] | None = None,
    count: int = 8,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    majors = load_major_characters(bible)
    if character_ids:
        want = set(character_ids)
        majors = [c for c in majors if c.get("id") in want]
    results = []
    n = max(1, min(int(count), 100))
    total_images = max(len(majors), 1) * n
    done_images = 0
    if on_progress:
        on_progress(0, total_images)
    for ch in majors:
        if should_cancel and should_cancel():
            break

        def _char_progress(done: int, _total: int, base: int = done_images) -> None:
            if on_progress:
                on_progress(base + done, total_images)

        result = generate_candidates_for_character(
            vpaths,
            ch,
            backend,
            count=n,
            should_cancel=should_cancel,
            on_progress=_char_progress,
        )
        results.append(result)
        done_images += len(result.get("files") or [])
        if on_progress:
            on_progress(done_images, total_images)
    return {"characters": results, "count": len(results)}
