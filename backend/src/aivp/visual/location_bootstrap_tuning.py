"""Location-scoped bootstrap tuning patches from judge failure tags."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths


def location_bootstrap_tuning_path(vpaths: VisualPaths, location_id: str) -> Path:
    return vpaths.location_dir(location_id) / "bootstrap_tuning.json"


def load_location_bootstrap_tuning(vpaths: VisualPaths, location_id: str) -> dict[str, Any]:
    path = location_bootstrap_tuning_path(vpaths, location_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def save_location_bootstrap_tuning(
    vpaths: VisualPaths, location_id: str, tuning: dict[str, Any]
) -> Path:
    path = location_bootstrap_tuning_path(vpaths, location_id)
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

    if share("has_people", "face_detected") >= 0.15:
        patches["full_empty_boost"] = True
        patches["candidate_cfg"] = 11.0
        patches["extra_negative"] = (
            "person, people, human, man, woman, child, face, portrait, "
            "character, crowd, silhouette figure"
        )
    if share("place_unreadable") >= 0.15:
        patches["place_token_boost"] = True
        patches["candidate_cfg"] = max(float(patches.get("candidate_cfg") or 0), 10.5)
    if share("too_tight_crop") >= 0.15:
        patches["wide_establishing_boost"] = True
        patches["extra_negative"] = (
            (patches.get("extra_negative") or "")
            + ", close-up, macro, tight crop, portrait framing"
        ).strip(", ")
    if share("busy_wrong_place") >= 0.15:
        patches["extra_negative"] = (
            (patches.get("extra_negative") or "")
            + ", wrong landmark, modern city, sci-fi, palace interiors mismatched"
        ).strip(", ")
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
            parts = [str(out["extra_negative"]), str(value)]
            out["extra_negative"] = ", ".join(
                dict.fromkeys(
                    p.strip() for chunk in parts for p in chunk.split(",") if p.strip()
                )
            )
            continue
        out[key] = value
    return out


def apply_location_failure_tags(
    vpaths: VisualPaths,
    location_id: str,
    tags: Counter[str] | list[str] | dict[str, int],
) -> dict[str, Any]:
    current = load_location_bootstrap_tuning(vpaths, location_id)
    merged = merge_tuning(current, patches_from_failure_tags(tags))
    save_location_bootstrap_tuning(vpaths, location_id, merged)
    return merged
