"""Generate empty-scene location candidate plates."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.location_bootstrap_tuning import load_location_bootstrap_tuning
from aivp.visual.location_look_lock import resolve_location_look_lock
from aivp.visual.location_profiles import ensure_location_profile, save_location_profile
from aivp.visual.location_prompts import (
    ESTABLISHING_VIEWS,
    EXPAND_VIEWS,
    apply_location_tuning_to_prompt,
    build_location_candidate_prompt,
    location_negative_for,
)
from aivp.visual.paths import VisualPaths


def _unique_stem(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def generate_location_candidates_for(
    vpaths: VisualPaths,
    location: dict,
    backend: ImageBackend,
    *,
    count: int = 8,
    negative: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    profile = ensure_location_profile(vpaths, location)
    lid = profile["location_id"]
    out_dir = vpaths.location_candidates_dir(lid)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    n = max(1, min(int(count), 100))
    tuning = load_location_bootstrap_tuning(vpaths, lid)
    neg = negative or location_negative_for(profile, tuning=tuning)
    ref_image, base_denoise = resolve_location_look_lock(vpaths, lid, profile)
    views = EXPAND_VIEWS if ref_image else ESTABLISHING_VIEWS
    batch = _unique_stem("loc_cand")
    seed_base = fresh_seed()
    if on_progress:
        on_progress(0, n)
    for i in range(n):
        if should_cancel and should_cancel():
            break
        view = views[i % len(views)]
        prompt = build_location_candidate_prompt(profile, view)
        prompt = apply_location_tuning_to_prompt(prompt, tuning)
        cfg = float(tuning.get("candidate_cfg") or (9.5 if ref_image else 10.5))
        denoise = 1.0
        if ref_image:
            denoise = min(0.72, max(0.45, float(base_denoise) + 0.04 * ((i % 3) - 1)))
            prompt = (
                f"{prompt}, same location architecture materials and layout as reference, "
                "empty scene no people, only mild camera or lighting change"
            )
        name = f"{batch}_{i + 1:03d}.png"
        dest = out_dir / name
        if on_progress:
            on_progress(len(created), n)
        backend.generate(
            prompt=prompt,
            negative=neg,
            dest=dest,
            seed=(seed_base + i) % (2_147_483_647 + 1),
            width=1024,
            height=768,
            ref_image=ref_image,
            denoise=denoise,
            cfg=cfg,
        )
        dest.with_suffix(".txt").write_text(prompt, encoding="utf-8")
        meta = {
            "location_id": lid,
            "look_lock": bool(ref_image),
            "denoise": denoise,
            "cfg": cfg,
        }
        dest.with_suffix(".json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        created.append(dest.name)
        if on_progress:
            on_progress(len(created), n)
    profile["status"] = "candidates_ready"
    profile["candidates_generated_at"] = datetime.now(timezone.utc).isoformat()
    save_location_profile(vpaths, profile)
    return {
        "location_id": lid,
        "files": created,
        "trigger": profile["trigger"],
        "look_lock": bool(ref_image),
    }
