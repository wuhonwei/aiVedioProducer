"""Evidence-grounded QA / rewrite for character prompt_zh and wardrobe."""
from __future__ import annotations

import re
from typing import Any

_WS = re.compile(r"\s+")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(v) for v in value if _text(v)).strip()
    return str(value).strip()


def collect_entity_evidence(entity: dict | None) -> str:
    if not isinstance(entity, dict):
        return ""
    parts = [
        _text(entity.get("evidence")),
        _text(entity.get("name")),
        _text(entity.get("canonical_name")),
        " ".join(_text(a) for a in (entity.get("aliases") or [])),
    ]
    for ev in entity.get("evidence_list") or []:
        if isinstance(ev, dict):
            parts.append(_text(ev.get("text") or ev.get("evidence")))
        else:
            parts.append(_text(ev))
    return _WS.sub(" ", " ".join(p for p in parts if p)).strip()


def _wardrobe_tokens(outfit: str) -> list[str]:
    raw = _text(outfit)
    if not raw:
        return []
    # Prefer multi-char clothing cues.
    keys = (
        "粗布",
        "家常",
        "衣衫",
        "长衫",
        "短衫",
        "披风",
        "劲装",
        "黑衣",
        "官服",
        "长袍",
        "交领",
        "布衣",
        "短褐",
        "斗笠",
        "蒙面",
        "玉佩",
    )
    hits = [k for k in keys if k in raw]
    if hits:
        return hits
    # Fallback: consecutive CJK bigrams from outfit string.
    chars = [c for c in raw if "\u4e00" <= c <= "\u9fff"]
    return ["".join(chars[i : i + 2]) for i in range(0, max(0, len(chars) - 1), 2)][:6]


def wardrobe_grounded(outfit: str, evidence: str) -> bool:
    """True if outfit is empty, or at least one wardrobe cue appears in evidence."""
    outfit = _text(outfit)
    if not outfit:
        return True
    evidence = _text(evidence)
    if not evidence:
        return False
    tokens = _wardrobe_tokens(outfit)
    if not tokens:
        return True
    return any(t in evidence for t in tokens)


def qa_character_description(
    profile: dict,
    entity: dict | None = None,
    *,
    llm: Any = None,
    max_rewrites: int = 3,
) -> dict[str, Any]:
    """Validate wardrobe/prompt against novel evidence; optionally rewrite via LLM.

    Returns ``{ok, profile, warnings, rewrites, evidence}``.
    """
    profile = dict(profile or {})
    evidence = collect_entity_evidence(entity)
    warnings: list[str] = []
    rewrites = 0
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    outfit = _text(wardrobe.get("default"))

    def _ok() -> bool:
        return wardrobe_grounded(outfit, evidence) if evidence else bool(outfit)

    if not evidence:
        warnings.append("description_qa_no_evidence")
        # Soft-pass when no evidence blob — cannot contradict novel text.
        return {
            "ok": True,
            "profile": profile,
            "warnings": warnings,
            "rewrites": 0,
            "evidence": evidence,
        }

    while not wardrobe_grounded(outfit, evidence) and rewrites < max(0, int(max_rewrites)):
        rewrites += 1
        if llm is None:
            warnings.append("description_qa_wardrobe_ungrounded")
            break
        try:
            raw = llm.complete_json(
                "You fix guofeng character wardrobe to match novel evidence. "
                "Output JSON with keys wardrobe_default (string) and prompt_zh (string). "
                "Use only cues present in evidence; do not invent luxury clothes.",
                f"name={profile.get('name')}\nevidence={evidence[:4000]}\n"
                f"current_wardrobe={outfit}\ncurrent_prompt={profile.get('prompt_zh') or ''}",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"description_qa_rewrite_failed:{exc}")
            break
        if not isinstance(raw, dict):
            warnings.append("description_qa_rewrite_invalid")
            break
        new_outfit = _text(raw.get("wardrobe_default") or raw.get("wardrobe"))
        new_prompt = _text(raw.get("prompt_zh"))
        if new_outfit:
            wardrobe = dict(wardrobe)
            wardrobe["default"] = new_outfit
            profile["wardrobe"] = wardrobe
            outfit = new_outfit
            inferred = list(profile.get("inferred_fields") or [])
            if "wardrobe.default" not in inferred:
                inferred.append("wardrobe.default")
            profile["inferred_fields"] = inferred
        if new_prompt:
            profile["prompt_zh"] = new_prompt
            inferred = list(profile.get("inferred_fields") or [])
            if "prompt_zh" not in inferred:
                inferred.append("prompt_zh")
            profile["inferred_fields"] = inferred

    ok = wardrobe_grounded(outfit, evidence)
    if not ok:
        warnings.append("description_needs_review")
    return {
        "ok": ok,
        "profile": profile,
        "warnings": warnings,
        "rewrites": rewrites,
        "evidence": evidence,
    }
