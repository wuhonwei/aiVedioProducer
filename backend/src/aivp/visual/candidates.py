from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.look_lock import resolve_look_lock
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, load_major_characters
from aivp.visual.prompts import build_candidate_prompt, candidate_negative_for


VIEW_PROMPTS = [
    "solo, 1person, facing camera, portrait, upper body, simple background",
    "solo, 1person, three quarter view, standing, full body, simple background",
    "solo, 1person, side profile, upper body, simple background",
    "solo, 1person, looking away, soft light, upper body, simple background",
    "solo, 1person, over the shoulder, dramatic light, simple background",
    "solo, 1person, close-up face, detailed eyes, simple background",
    "solo, 1person, walking pose, full body, simple background",
    "solo, 1person, sitting pose, medium shot, simple background",
]


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
    ref_image, denoise = resolve_look_lock(vpaths, cid, profile)
    batch = _unique_stem("cand")
    # New base each batch so Comfy does not replay the same 8 seeds forever.
    seed_base = fresh_seed()
    if on_progress:
        on_progress(0, n)
    for i in range(n):
        if should_cancel and should_cancel():
            break
        view = VIEW_PROMPTS[i % len(VIEW_PROMPTS)]
        prompt = build_candidate_prompt(profile, view)
        if ref_image:
            prompt = (
                f"{prompt}, keep same character identity and outfit as reference, "
                "consistent face and wardrobe"
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
            denoise=denoise if ref_image else 1.0,
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
        "denoise": denoise if ref_image else 1.0,
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
