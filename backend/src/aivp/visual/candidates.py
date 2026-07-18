from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.look_lock import (
    candidate_cfg_for,
    candidate_denoise_for,
    resolve_look_lock,
)
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, load_major_characters, save_profile
from aivp.visual.prompts import build_candidate_prompt, candidate_negative_for
from aivp.visual.qa_tuning import load_qa_tuning


VIEW_PROMPTS = [
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, facing camera, standing, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, three quarter view, standing, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, side profile standing, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, looking away, standing, soft light, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, slight contrapposto standing pose, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, walking pose, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, standing hands at sides, plain background",
    "solo, 1person, wide shot, full body, head to toe, feet visible, shoes visible, standing relaxed pose, plain background",
]

# Look-lock: mild camera / stance change only — dramatic actions break outfit + framing.
LOOK_LOCK_ACTION_PROMPTS = [
    "full body head to toe feet visible, facing camera, standing neutral, arms relaxed at sides, plain background",
    "full body head to toe feet visible, slight three quarter view, standing, weight on one leg, plain background",
    "full body head to toe feet visible, facing camera, standing hands clasped at waist, plain background",
    "full body head to toe feet visible, mild body turn, standing respectful posture, plain background",
    "full body head to toe feet visible, facing camera, standing relaxed contrapposto, plain background",
    "full body head to toe feet visible, three quarter view, standing, one hand lightly at side, plain background",
    "full body head to toe feet visible, facing camera, standing, both arms naturally at sides, plain background",
    "full body head to toe feet visible, slight turn toward camera, standing composed pose, plain background",
]

_FRAMING_LOCK = (
    "full body, head to toe, feet visible, entire figure in frame, "
    "shoes or feet on ground, not cropped at waist, not portrait crop"
)


def _look_lock_candidate_negative(base_neg: str) -> str:
    extra = (
        "different face, different hairstyle, different hair color, different outfit, "
        "costume change, clothing redesign, wardrobe change, new clothes, "
        "different sleeve length, different collar, different garment color, "
        "recolored clothes, pattern change, accessory change, "
        "shirtless, bare chest, topless, nude, naked, open shirt, exposed midriff, "
        "face morph, identity drift, age change, gender change, "
        "half body, waist up, portrait crop, close-up, bust shot, cropped legs, "
        "missing feet, floating limbs, detached foot, extra limbs, "
        "armor redesign, random costume, modern clothes"
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
    n = max(1, min(int(count), 100))
    neg = negative or candidate_negative_for(profile)
    # Full-body look-lock ref keeps outfit; face-only canvas caused costume/framing chaos.
    ref_image, base_denoise = resolve_look_lock(vpaths, cid, profile)
    ref_kind = "full" if ref_image else "none"
    tuning = dict(load_qa_tuning(vpaths) or {})
    # Character-local bootstrap patches override project QA tuning.
    from aivp.visual.bootstrap_tuning import load_bootstrap_tuning

    bt = load_bootstrap_tuning(vpaths, cid)
    if bt:
        for key, value in bt.items():
            if key == "reason_tags":
                continue
            if key == "extra_negative" and tuning.get("extra_negative") and value:
                tuning["extra_negative"] = (
                    f"{tuning['extra_negative']}, {value}"
                )
            else:
                tuning[key] = value
    if ref_image:
        neg = _look_lock_candidate_negative(neg)
    if tuning.get("extra_negative"):
        neg = f"{neg}, {tuning['extra_negative']}"
    if tuning.get("plain_background") or tuning.get("full_body_boost"):
        neg = (
            f"{neg}, half body, waist up, bust shot, portrait crop, "
            "busy scenery, detailed background"
        )
    batch = _unique_stem("cand")
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
        # Higher CFG so full-body framing beats elder-face portrait priors.
        cfg = float(tuning.get("candidate_cfg") or (10.5 if not ref_image else 8.0))
        if ref_image:
            denoise = candidate_denoise_for(
                view, base_denoise, index=i, tuning=tuning, ref_kind="full"
            )
            used_denoises.append(denoise)
            cfg = float(tuning.get("candidate_cfg") or candidate_cfg_for(ref_kind="full"))
            prompt = (
                f"{prompt}, {_FRAMING_LOCK}, "
                "exact same face hairstyle hair color and outfit as reference photo, "
                "identical clothing colors seams accessories fabric and silhouette, "
                "fully clothed covered chest closed collar, "
                "only mild camera angle or stance change, keep same costume, "
                "do not redesign wardrobe or facial features, "
                "no half-body crop, no floating limbs, no shirtless"
            )
        if tuning.get("full_body_boost"):
            prompt = (
                f"{prompt}, {_FRAMING_LOCK}, head to toe, feet and shoes clearly visible"
            )
        if tuning.get("outfit_lock_boost"):
            prompt = (
                f"{prompt}, fully clothed, covered torso, exact wardrobe colors, "
                "guofeng cloak or tunic as described, no bare chest"
            )
        if tuning.get("identity_lock_boost"):
            prompt = (
                f"{prompt}, exact same face as character card, preserve age and gender"
            )
        name = f"{batch}_{i+1:03d}.png"
        dest = out_dir / name
        if on_progress:
            on_progress(len(created), n)
        try:
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
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"candidate_{i + 1}_of_{n}_failed:{exc}") from exc
        dest.with_suffix(".txt").write_text(prompt, encoding="utf-8")
        meta_path = dest.with_suffix(".json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    meta["look_lock_ref_kind"] = ref_kind if ref_image else None
                    meta_path.write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            except Exception:  # noqa: BLE001
                pass
        created.append(dest.name)
        if on_progress:
            on_progress(len(created), n)
    profile["status"] = "candidates_ready"
    profile["candidates_generated_at"] = datetime.now(timezone.utc).isoformat()
    if ref_image:
        profile["candidates_used_look_lock"] = True
        profile["candidates_look_lock_ref_kind"] = ref_kind
    save_profile(vpaths, profile)
    return {
        "character_id": cid,
        "files": created,
        "trigger": profile["trigger"],
        "look_lock": bool(ref_image),
        "look_lock_ref_kind": ref_kind if ref_image else None,
        "denoise": (
            sum(used_denoises) / len(used_denoises)
            if used_denoises
            else (base_denoise if ref_image else 1.0)
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

        def _char_progress(done: int, _total: int) -> None:
            if on_progress:
                on_progress(done_images + done, total_images)

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
