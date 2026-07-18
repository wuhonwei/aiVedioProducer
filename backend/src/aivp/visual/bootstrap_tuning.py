"""Character-scoped bootstrap tuning patches derived from judge failure tags."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths


def bootstrap_tuning_path(vpaths: VisualPaths, character_id: str) -> Path:
    return vpaths.character_dir(character_id) / "bootstrap_tuning.json"


def load_bootstrap_tuning(vpaths: VisualPaths, character_id: str) -> dict[str, Any]:
    path = bootstrap_tuning_path(vpaths, character_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def save_bootstrap_tuning(
    vpaths: VisualPaths, character_id: str, tuning: dict[str, Any]
) -> Path:
    path = bootstrap_tuning_path(vpaths, character_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tuning, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def patches_from_failure_tags(tags: Counter[str] | list[str] | dict[str, int]) -> dict[str, Any]:
    if isinstance(tags, Counter):
        counts = tags
    elif isinstance(tags, dict):
        counts = Counter({str(k): int(v) for k, v in tags.items()})
    else:
        counts = Counter(str(t) for t in tags)
    patches: dict[str, Any] = {"reason_tags": dict(counts.most_common(12))}
    total = sum(counts.values()) or 1

    def share(*keys: str) -> float:
        return sum(counts.get(k, 0) for k in keys) / total

    if share("half_body", "cropped_feet", "bad_framing", "waist_up") >= 0.2:
        patches["candidate_cfg"] = 11.5
        patches["full_body_boost"] = True
        patches["extra_negative"] = (
            "half body, waist up, bust shot, portrait crop, cropped feet, missing shoes"
        )
    if share("busy_background") >= 0.15:
        patches["plain_background"] = True
        patches["extra_negative"] = (
            (patches.get("extra_negative") or "")
            + ", busy scenery, palace, forest bokeh, crowded background"
        ).strip(", ")
    if share("shirtless_or_revealing", "wrong_outfit", "incomplete_outfit") >= 0.2:
        patches["outfit_lock_boost"] = True
        patches["candidate_denoise_hi"] = 0.62
    if share("wrong_emotion", "bad_expression") >= 0.15:
        patches["expr_denoise"] = 0.88
        patches["expr_cfg"] = 12.5
    if share("identity_drift", "wrong_gender", "too_young") >= 0.15:
        patches["candidate_denoise_hi"] = min(float(patches.get("candidate_denoise_hi") or 0.66), 0.58)
        patches["identity_lock_boost"] = True
    return patches


def merge_tuning(existing: dict[str, Any], patches: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing or {})
    for key, value in (patches or {}).items():
        if key == "reason_tags" and isinstance(value, dict):
            prev = out.get("reason_tags") if isinstance(out.get("reason_tags"), dict) else {}
            merged = Counter(prev)
            merged.update({str(k): int(v) for k, v in value.items()})
            out["reason_tags"] = dict(merged)
            continue
        if key == "extra_negative" and out.get("extra_negative") and value:
            # Dedup-ish join
            parts = [str(out["extra_negative"]), str(value)]
            out["extra_negative"] = ", ".join(dict.fromkeys(
                p.strip() for chunk in parts for p in chunk.split(",") if p.strip()
            ))
            continue
        out[key] = value
    return out


def apply_failure_tags(
    vpaths: VisualPaths,
    character_id: str,
    tags: Counter[str] | list[str] | dict[str, int],
) -> dict[str, Any]:
    current = load_bootstrap_tuning(vpaths, character_id)
    merged = merge_tuning(current, patches_from_failure_tags(tags))
    save_bootstrap_tuning(vpaths, character_id, merged)
    return merged
