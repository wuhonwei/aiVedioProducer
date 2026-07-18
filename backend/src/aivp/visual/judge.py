from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from aivp.visual.prompts import normalize_gender, wardrobe_english_tokens


class VisionJudge(Protocol):
    def complete_json_with_image(
        self,
        system: str,
        user: str,
        image_path: Path,
        *,
        should_cancel: Any = None,
    ) -> dict[str, Any]: ...


JUDGE_SYSTEM = """You are a strict QA judge for guofeng anime character reference images.
Return ONLY JSON. Be conservative: fail if clothing is revealing, wrong gender, wrong camera view, or wrong framing.
Do not invent details that are not visible."""


def _slot_kind(slot_key: str | None) -> str:
    key = (slot_key or "").strip().lower()
    if key.startswith("expr_"):
        return "expression"
    if key.startswith("turnaround_"):
        return "turnaround"
    return "candidate"


def _expected_view(slot_key: str | None) -> str:
    key = (slot_key or "").strip().lower()
    if key == "turnaround_front":
        return "front view facing camera"
    if key == "turnaround_side":
        return "strict side profile 90 degrees"
    if key == "turnaround_back":
        return "rear view from behind, no face"
    if key.startswith("expr_"):
        return "face-only close-up headshot"
    return "full body character shot"


def build_judge_user_prompt(
    profile: dict,
    *,
    slot_key: str | None = None,
    expected_label: str | None = None,
) -> str:
    kind = _slot_kind(slot_key)
    gender = normalize_gender(
        profile.get("gender_presentation"),
        text_hints=f"{profile.get('prompt_zh') or ''} {profile.get('name') or ''}",
    )
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    outfit = str(wardrobe.get("default") or "").strip()
    colors = wardrobe.get("colors") if isinstance(wardrobe.get("colors"), list) else []
    en = ", ".join(wardrobe_english_tokens(outfit, colors=[str(c) for c in colors]))
    age = str(profile.get("age_look") or "").strip()
    look = str(profile.get("prompt_zh") or "").strip()
    view = _expected_view(slot_key)
    expr = expected_label or (slot_key or "candidate")

    requirements = {
        "kind": kind,
        "name": profile.get("name"),
        "gender": gender,
        "age_look": age,
        "outfit_zh": outfit,
        "outfit_en_hints": en,
        "look_prompt_zh": look,
        "expected_view_or_framing": view,
        "slot": expr,
        "must": [
            "gender matches",
            "apparent age matches age_look (elderly must look old; middle-aged not youthful idol)",
            "torso fully clothed (no shirtless / bare chest / open shirt)",
            "outfit roughly matches described guofeng clothing and colors",
            "framing matches expected_view_or_framing",
        ],
    }
    if kind == "expression":
        requirements["must"].append("face/head only — no full body, no visible legs/feet")
    if kind == "turnaround":
        requirements["must"].append("full body head-to-toe with feet visible")
        requirements["must"].append(
            "camera view_angle must match expected_view_or_framing exactly "
            "(side must be 90° profile; back must show no face)"
        )
    if kind == "candidate":
        requirements["must"].append("full body head-to-toe with feet visible")
    if age and any(k in age for k in ("老年", "花甲", "婆婆", "五十", "沧桑", "中年")):
        requirements["must"].append(
            "reject youthful anime-idol face if age_look implies middle-aged or elderly"
        )

    return (
        "Judge whether this image matches the character requirements.\n"
        f"requirements={json.dumps(requirements, ensure_ascii=False)}\n"
        "Respond JSON schema:\n"
        "{"
        '"pass": bool, '
        '"score": number 0-1, '
        '"summary": string, '
        '"checks": {'
        '"gender": {"pass": bool, "note": string}, '
        '"age": {"pass": bool, "note": string}, '
        '"clothing_covered": {"pass": bool, "note": string}, '
        '"outfit_match": {"pass": bool, "note": string}, '
        '"framing": {"pass": bool, "note": string}, '
        '"view_angle": {"pass": bool, "note": string}'
        "}, "
        '"failure_tags": [string]  // e.g. shirtless, wrong_outfit, wrong_view_front, too_young, full_body_instead_of_face, wrong_gender, cropped_feet'
        "}"
    )


def normalize_judge_result(raw: dict[str, Any]) -> dict[str, Any]:
    checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    tags = raw.get("failure_tags") if isinstance(raw.get("failure_tags"), list) else []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    # Soft hard-fail gates from checks.
    hard = ("clothing_covered", "gender", "framing", "age", "view_angle")
    hard_fail = False
    for key in hard:
        item = checks.get(key)
        if isinstance(item, dict) and item.get("pass") is False:
            hard_fail = True
            if key == "clothing_covered" and "shirtless" not in tags:
                tags.append("shirtless_or_revealing")
            if key == "gender" and "wrong_gender" not in tags:
                tags.append("wrong_gender")
            if key == "framing" and "bad_framing" not in tags:
                tags.append("bad_framing")
            if key == "age" and "too_young" not in tags:
                tags.append("too_young")
            if key == "view_angle" and "wrong_view" not in tags:
                tags.append("wrong_view")
    score = float(raw.get("score") or 0.0)
    score = max(0.0, min(1.0, score))
    passed = bool(raw.get("pass")) and not hard_fail and score >= 0.55
    return {
        "pass": passed,
        "score": score,
        "summary": str(raw.get("summary") or ""),
        "checks": checks,
        "failure_tags": tags,
    }


def judge_image(
    vision: VisionJudge,
    profile: dict,
    image_path: Path,
    *,
    slot_key: str | None = None,
    expected_label: str | None = None,
) -> dict[str, Any]:
    user = build_judge_user_prompt(
        profile, slot_key=slot_key, expected_label=expected_label
    )
    raw = vision.complete_json_with_image(JUDGE_SYSTEM, user, Path(image_path))
    result = normalize_judge_result(raw)
    result["image"] = Path(image_path).name
    result["slot_key"] = slot_key
    return result
