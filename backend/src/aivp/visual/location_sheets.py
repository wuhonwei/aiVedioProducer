"""Location sheet plates: angles / TOD / weather / materials."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from aivp.visual.image_backend import ImageBackend, fresh_seed
from aivp.visual.location_bootstrap_tuning import load_location_bootstrap_tuning
from aivp.visual.location_look_lock import resolve_location_look_lock
from aivp.visual.location_profiles import ensure_location_profile, save_location_profile
from aivp.visual.location_prompts import (
    apply_location_tuning_to_prompt,
    build_location_candidate_prompt,
    location_negative_for,
)
from aivp.visual.paths import VisualPaths

LOCATION_SHEET_SLOTS: dict[str, str] = {
    "establishing_wide": "ultra wide establishing empty scenery, no people",
    "angle_three_quarter": "three quarter empty environmental angle, no humans",
    "angle_side": "side view empty architecture, no characters",
    "tod_dawn": "dawn mist empty place, soft light, no people",
    "tod_dusk": "dusk empty scenery, warm rim light, no humans",
    "weather_fog": "foggy empty environment, atmospheric depth, no people",
    "material_stone": "close material study of stone surfaces of this place, empty, no people",
    "material_wood": "close material study of wood structures of this place, empty, no people",
}


def generate_location_sheets(
    vpaths: VisualPaths,
    location: dict,
    backend: ImageBackend,
    *,
    slot_keys: list[str] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    profile = ensure_location_profile(vpaths, location)
    lid = profile["location_id"]
    out_dir = vpaths.location_sheets_dir(lid)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = slot_keys or list(LOCATION_SHEET_SLOTS.keys())
    tuning = load_location_bootstrap_tuning(vpaths, lid)
    neg = location_negative_for(profile, tuning=tuning)
    ref_image, base_denoise = resolve_location_look_lock(vpaths, lid, profile)
    created: list[dict[str, str]] = []
    seed_base = fresh_seed()
    for i, key in enumerate(keys):
        if should_cancel and should_cancel():
            break
        view = LOCATION_SHEET_SLOTS.get(key) or key
        prompt = build_location_candidate_prompt(profile, view)
        prompt = apply_location_tuning_to_prompt(prompt, tuning)
        denoise = 1.0
        cfg = float(tuning.get("candidate_cfg") or 10.0)
        if ref_image:
            denoise = min(0.78, max(0.48, float(base_denoise) + (0.05 if "material" in key else 0.0)))
            prompt = (
                f"{prompt}, same location as reference photo, empty scene no people"
            )
        name = f"sheet_{key}_{uuid4().hex[:8]}.png"
        dest = out_dir / name
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
        created.append({"key": key, "file": name})
    save_location_profile(vpaths, profile)
    return {"location_id": lid, "files": created}
