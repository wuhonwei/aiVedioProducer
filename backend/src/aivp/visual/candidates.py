from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from aivp.visual.image_backend import ImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, load_major_characters
from aivp.visual.prompts import character_negative_for


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


def build_candidate_prompt(profile: dict, view: str) -> str:
    trigger = profile.get("trigger") or "character_aivp"
    base = profile.get("prompt_zh") or profile.get("name") or trigger
    anchors = "，".join(profile.get("consistency_anchors") or [])
    wardrobe = ""
    w = profile.get("wardrobe") or {}
    if isinstance(w, dict):
        wardrobe = str(w.get("default") or "")
    parts = [
        trigger,
        str(base),
        wardrobe,
        anchors,
        view,
        "guofeng anime style, consistent character design, masterpiece",
    ]
    return "，".join([p for p in parts if p])


def generate_candidates_for_character(
    vpaths: VisualPaths,
    character: dict,
    backend: ImageBackend,
    *,
    count: int = 8,
    negative: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    profile = ensure_profile(vpaths, character)
    cid = profile["character_id"]
    out_dir = vpaths.candidates_dir(cid)
    created: list[str] = []
    n = max(1, min(count, len(VIEW_PROMPTS)))
    neg = negative or character_negative_for(str(profile.get("gender_presentation") or ""))
    for i in range(n):
        if should_cancel and should_cancel():
            break
        view = VIEW_PROMPTS[i % len(VIEW_PROMPTS)]
        prompt = build_candidate_prompt(profile, view)
        dest = out_dir / f"cand_{i+1:02d}.png"
        backend.generate(
            prompt=prompt,
            negative=neg,
            dest=dest,
            seed=1000 + i,
            width=768,
            height=1024,
        )
        # caption for later training
        (out_dir / f"cand_{i+1:02d}.txt").write_text(
            f"{profile['trigger']}, {view}, {profile.get('prompt_zh') or ''}".strip(),
            encoding="utf-8",
        )
        created.append(dest.name)
    profile["status"] = "candidates_ready"
    profile["candidates_generated_at"] = datetime.now(timezone.utc).isoformat()
    vpaths.profile_json(cid).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"character_id": cid, "files": created, "trigger": profile["trigger"]}


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
    total = max(len(majors), 1)
    for i, ch in enumerate(majors):
        if should_cancel and should_cancel():
            break
        results.append(
            generate_candidates_for_character(
                vpaths, ch, backend, count=count, should_cancel=should_cancel
            )
        )
        if on_progress:
            on_progress(i + 1, total)
    return {"characters": results, "count": len(results)}
