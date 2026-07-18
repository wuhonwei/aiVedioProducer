"""Vision judge for empty-scene location plates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def is_location_look_lock_eligible(judged: dict) -> bool:
    checks = judged.get("checks") if isinstance(judged.get("checks"), dict) else {}
    required = (
        "no_people",
        "place_readable",
        "establishing_or_env",
        "not_character_sheet",
    )
    for key in required:
        item = checks.get(key) if isinstance(checks.get(key), dict) else {}
        if not item.get("pass"):
            return False
    # style_match soft: prefer pass but allow if overall pass + score
    style = checks.get("style_match") if isinstance(checks.get("style_match"), dict) else {}
    if style and style.get("pass") is False and float(judged.get("score") or 0) < 0.55:
        return False
    return bool(judged.get("pass", True))


def _normalize_location_judge(raw: dict) -> dict[str, Any]:
    checks_in = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    checks: dict[str, Any] = {}
    failure_tags: list[str] = []

    def _as_check(key: str, *, default_pass: bool = True) -> dict:
        item = checks_in.get(key)
        if isinstance(item, dict):
            ok = bool(item.get("pass", default_pass))
            note = str(item.get("note") or "")
        elif isinstance(item, bool):
            ok = item
            note = ""
        else:
            ok = default_pass
            note = ""
        return {"pass": ok, "note": note}

    for key in (
        "no_people",
        "place_readable",
        "establishing_or_env",
        "style_match",
        "not_character_sheet",
    ):
        checks[key] = _as_check(key, default_pass=(key != "no_people"))

    if not checks["no_people"]["pass"]:
        failure_tags.append("has_people")
    if not checks["place_readable"]["pass"]:
        failure_tags.append("place_unreadable")
    if not checks["establishing_or_env"]["pass"]:
        failure_tags.append("too_tight_crop")
    if not checks["style_match"]["pass"]:
        failure_tags.append("busy_wrong_place")
    if not checks["not_character_sheet"]["pass"]:
        failure_tags.append("has_people")

    hard_ok = all(
        checks[k]["pass"]
        for k in ("no_people", "place_readable", "establishing_or_env", "not_character_sheet")
    )
    score = float(raw.get("score") or (0.8 if hard_ok else 0.3))
    return {
        "pass": hard_ok and bool(raw.get("pass", hard_ok)),
        "score": score,
        "summary": str(raw.get("summary") or ""),
        "checks": checks,
        "failure_tags": list(dict.fromkeys(failure_tags + list(raw.get("failure_tags") or []))),
    }


def judge_location_image(
    vision: Any,
    profile: dict,
    image_path: Path,
    *,
    slot_key: str | None = None,
) -> dict[str, Any]:
    name = str(profile.get("name") or "")
    prompt_zh = str(profile.get("prompt_zh") or "")
    materials = profile.get("materials") or []
    palette = profile.get("palette") or []
    user = (
        "Judge this EMPTY LOCATION plate for LoRA training. "
        "Return JSON with keys: pass (bool), score (0-1), summary, checks, failure_tags. "
        "checks must include: no_people, place_readable, establishing_or_env, style_match, "
        "not_character_sheet — each {pass, note}. "
        "FAIL no_people if any readable face or clear human body. "
        "FAIL establishing_or_env if tight portrait-like crop of a person or random texture. "
        f"Location card: name={name}; prompt_zh={prompt_zh}; materials={materials}; "
        f"palette={palette}; slot={slot_key or 'candidate'}."
    )
    try:
        raw = vision.complete_vision_json(user, image_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "score": 0.0,
            "summary": f"vision_error:{exc}",
            "checks": {
                "no_people": {"pass": False, "note": "vision_error"},
                "place_readable": {"pass": False, "note": "vision_error"},
                "establishing_or_env": {"pass": False, "note": "vision_error"},
                "style_match": {"pass": False, "note": "vision_error"},
                "not_character_sheet": {"pass": False, "note": "vision_error"},
            },
            "failure_tags": ["vision_error"],
            "image": image_path.name,
            "slot_key": slot_key,
        }
    if not isinstance(raw, dict):
        try:
            raw = json.loads(str(raw))
        except Exception:  # noqa: BLE001
            raw = {}
    out = _normalize_location_judge(raw if isinstance(raw, dict) else {})
    out["image"] = image_path.name
    out["slot_key"] = slot_key
    return out
