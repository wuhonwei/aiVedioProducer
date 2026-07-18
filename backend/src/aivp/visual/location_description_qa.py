"""Evidence-grounded QA for location prompt_zh / palette / materials."""
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


def _tokens_from_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out = []
    for v in values:
        t = _text(v)
        if len(t) >= 2:
            out.append(t)
    return out


def _grounded_overlap(claim: str, evidence: str) -> bool:
    claim = _WS.sub("", claim)
    evidence = _WS.sub("", evidence)
    if not claim or not evidence:
        return False
    if claim in evidence or evidence in claim:
        return True
    # Bigram-ish: any 2+ char chunk of claim in evidence
    for i in range(len(claim) - 1):
        chunk = claim[i : i + 2]
        if chunk in evidence:
            return True
    return False


def qa_location_description(
    profile: dict,
    entity: dict | None,
    *,
    llm: Any = None,
    max_rewrites: int = 3,
) -> dict[str, Any]:
    """Check location look claims against evidence; optionally rewrite via LLM."""
    profile = dict(profile or {})
    warnings: list[str] = []
    rewrites = 0
    evidence = collect_entity_evidence(entity)
    name = _text(profile.get("name") or (entity or {}).get("name"))

    def _check() -> tuple[bool, list[str]]:
        local_warn: list[str] = []
        if not evidence:
            local_warn.append("no_evidence")
            return False, local_warn
        prompt = _text(profile.get("prompt_zh"))
        materials = _tokens_from_list(profile.get("materials"))
        palette = _tokens_from_list(profile.get("palette"))
        ok_bits = 0
        if name and (name in evidence or _grounded_overlap(name, evidence)):
            ok_bits += 1
        for m in materials:
            if _grounded_overlap(m, evidence) or m in prompt and _grounded_overlap(m, evidence):
                ok_bits += 1
            elif m and m not in evidence and not _grounded_overlap(m, evidence):
                local_warn.append(f"ungrounded_material:{m}")
        for p in palette:
            if _grounded_overlap(p, evidence):
                ok_bits += 1
        if prompt and _grounded_overlap(prompt[:24], evidence):
            ok_bits += 1
        elif prompt and not any(_grounded_overlap(t, evidence) for t in materials + palette + [name]):
            local_warn.append("ungrounded_prompt_zh")
        # Pass if name or any material/palette overlaps evidence.
        if ok_bits >= 1 and not any(w.startswith("ungrounded_prompt") for w in local_warn):
            return True, local_warn
        if ok_bits >= 1 and materials and all(
            _grounded_overlap(m, evidence) for m in materials[:2]
        ):
            return True, local_warn
        if ok_bits >= 1:
            # Soft: name/material hit is enough even with soft prompt warning
            return True, local_warn
        return False, local_warn or ["ungrounded_location_look"]

    ok, warnings = _check()
    while (not ok) and llm is not None and rewrites < max(0, int(max_rewrites)):
        rewrites += 1
        try:
            rewritten = llm.complete_json(
                "You rewrite location visual cards. Only use facts from evidence. "
                "Return JSON keys: prompt_zh, materials (list), palette (list). Chinese.",
                f"evidence:\n{evidence}\n\ncurrent:\n{json_dumps(profile)}",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"rewrite_failed:{exc}")
            break
        if isinstance(rewritten, dict):
            if rewritten.get("prompt_zh"):
                profile["prompt_zh"] = _text(rewritten["prompt_zh"])
            if isinstance(rewritten.get("materials"), list):
                profile["materials"] = [_text(x) for x in rewritten["materials"] if _text(x)]
            if isinstance(rewritten.get("palette"), list):
                profile["palette"] = [_text(x) for x in rewritten["palette"] if _text(x)]
            inferred = list(profile.get("inferred_fields") or [])
            for key in ("prompt_zh", "materials", "palette"):
                if key not in inferred:
                    inferred.append(key)
            profile["inferred_fields"] = inferred
        ok, warnings = _check()

    if not ok and "no_evidence" not in warnings:
        inferred = list(profile.get("inferred_fields") or [])
        if "prompt_zh" not in inferred:
            inferred.append("prompt_zh")
        profile["inferred_fields"] = inferred
    return {
        "ok": ok,
        "profile": profile,
        "warnings": warnings,
        "rewrites": rewrites,
    }


def json_dumps(profile: dict) -> str:
    import json

    return json.dumps(
        {
            "name": profile.get("name"),
            "prompt_zh": profile.get("prompt_zh"),
            "materials": profile.get("materials"),
            "palette": profile.get("palette"),
        },
        ensure_ascii=False,
    )
