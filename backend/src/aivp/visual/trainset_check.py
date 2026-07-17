from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths


def _image_type(name: str) -> str:
    n = name.lower()
    if "turnaround_front" in n or "front" in n and "turnaround" in n:
        return "turnaround_front"
    if "turnaround_side" in n or ("side" in n and "turnaround" in n):
        return "turnaround_side"
    if "turnaround_back" in n or ("back" in n and "turnaround" in n):
        return "turnaround_back"
    if "turnaround" in n:
        return "turnaround"
    if "expr_" in n or "expression" in n:
        return "expression"
    if n.startswith("cand_") or "portrait" in n:
        return "candidate_portrait"
    return "reference"


def check_trainset(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    profile = (
        json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    )
    trigger = str(profile.get("trigger") or "")
    curated = sorted(vpaths.curated_dir(character_id).glob("*.png"))
    sources = profile.get("curated_sources") if isinstance(profile.get("curated_sources"), list) else []
    by_file = {str(s.get("file")): str(s.get("folder")) for s in sources if isinstance(s, dict)}

    missing_captions: list[str] = []
    trigger_mismatch: list[str] = []
    turnaround = 0
    expression = 0
    candidate = 0
    has_front = False
    has_side = False
    has_back = False

    for img in curated:
        name = img.name
        itype = _image_type(name)
        folder = by_file.get(name) or (
            "sheets" if "turnaround" in name or "expr_" in name else "candidates"
        )
        if folder == "sheets" or "turnaround" in name or "expr_" in name:
            if "turnaround" in name:
                turnaround += 1
            if "expr_" in name or "expression" in name:
                expression += 1
        else:
            candidate += 1
        if itype == "turnaround_front" or "front" in name.lower():
            has_front = True
        if itype == "turnaround_side" or "side" in name.lower():
            has_side = True
        if itype == "turnaround_back" or "back" in name.lower():
            has_back = True

        cap = img.with_suffix(".txt")
        if not cap.exists() or not cap.read_text(encoding="utf-8").strip():
            missing_captions.append(name)
            continue
        text = cap.read_text(encoding="utf-8")
        if trigger and trigger not in text:
            trigger_mismatch.append(name)

    image_count = len(curated)
    caption_count = image_count - len(missing_captions)
    warnings: list[str] = []
    if image_count < 8:
        warnings.append("image_count_below_recommended_8")
    if image_count < 6:
        warnings.append("image_count_below_minimum_6")
    if turnaround < 3:
        warnings.append("turnaround_incomplete")
    if expression < 4:
        warnings.append("expression_below_recommended_4")
    if candidate < 4:
        warnings.append("candidate_below_recommended_4")
    if missing_captions:
        warnings.append("missing_captions")
    if trigger_mismatch:
        warnings.append("trigger_mismatch")
    if not has_front:
        warnings.append("missing_front_view")

    can_train = (
        image_count >= 8
        and caption_count == image_count
        and not trigger_mismatch
        and has_front
        and bool(trigger)
    )
    # Soft score 0-100
    score = 0
    score += min(40, image_count * 2)
    score += 20 if caption_count == image_count and image_count else 0
    score += 15 if not trigger_mismatch and trigger else 0
    score += 10 if has_front else 0
    score += 5 if has_side else 0
    score += 5 if has_back else 0
    score += 5 if expression >= 4 else 0

    return {
        "character_id": character_id,
        "trigger": trigger,
        "image_count": image_count,
        "caption_count": caption_count,
        "candidate_count": candidate,
        "turnaround_count": turnaround,
        "expression_count": expression,
        "has_front": has_front,
        "has_side": has_side,
        "has_back": has_back,
        "missing_captions": missing_captions,
        "trigger_mismatch": trigger_mismatch,
        "warnings": warnings,
        "can_train": can_train,
        "score": min(100, score),
    }
