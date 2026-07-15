from __future__ import annotations

from typing import Any

from aivp.pipeline.character_looks import seed_character_look


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(v) for v in value if _text(v)).strip()
    return str(value).strip()


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        t = _text(item)
        if t and t not in out:
            out.append(t)
    return out


def ensure_character_card(entity: dict, raw: dict | None, *, tier: str) -> dict[str, Any]:
    raw = raw or {}
    name = _text(entity.get("name") or raw.get("name"))
    seed = seed_character_look(entity) if tier == "major" else None
    appearance = raw.get("appearance") if isinstance(raw.get("appearance"), dict) else {}
    wardrobe = raw.get("wardrobe") if isinstance(raw.get("wardrobe"), dict) else {}
    voice = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
    seed_app = (seed or {}).get("appearance") or {}
    seed_ward = (seed or {}).get("wardrobe") or {}

    face = _text(appearance.get("face")) or (
        _text(seed_app.get("face")) if seed else ""
    )
    hair = _text(appearance.get("hair")) or (
        _text(seed_app.get("hair")) if seed else ""
    )
    body = _text(appearance.get("body")) or (
        _text(seed_app.get("body")) if seed else ""
    )
    marks = _text(appearance.get("distinctive_marks")) or (
        _text(seed_app.get("distinctive_marks")) if seed else ""
    )
    wardrobe_default = _text(wardrobe.get("default")) or (
        _text(seed_ward.get("default")) if seed else ""
    )
    colors = _str_list(wardrobe.get("colors")) or (
        list(seed_ward.get("colors") or []) if seed else []
    )
    timbre = _text(voice.get("timbre")) or (
        "中青年清柔女声"
        if seed and seed.get("gender_presentation") == "feminine"
        else ("中青年清柔男声" if tier == "major" else "")
    )
    age_look = _text(raw.get("age_look")) or (
        _text(seed.get("age_look")) if seed else ""
    )
    prompt = _text(raw.get("prompt_zh"))
    if not prompt and seed:
        prompt = _text(seed.get("prompt_zh"))
    if not prompt and tier == "major" and name:
        prompt = (
            f"{name}，{age_look or '角色'}，{hair}，{face}，"
            f"身着{wardrobe_default or '常服'}，国风动画角色定妆"
        )
    fallback_tag = wardrobe_default or face or "配角"
    brief = _text(raw.get("brief")) or ("%s：%s" % (name, fallback_tag))
    inferred = _str_list(raw.get("inferred_fields"))
    for field, filled in [
        ("appearance.face", face and not _text((appearance or {}).get("face"))),
        ("wardrobe.default", wardrobe_default and not _text((wardrobe or {}).get("default"))),
        ("voice.timbre", timbre and not _text((voice or {}).get("timbre"))),
        ("prompt_zh", prompt and not _text(raw.get("prompt_zh"))),
    ]:
        if filled and field not in inferred:
            inferred.append(field)

    evidence = _str_list(raw.get("evidence"))
    for e in (seed or {}).get("evidence") or []:
        if e and e not in evidence:
            evidence.append(e)
    if _text(entity.get("evidence")) and _text(entity.get("evidence")) not in evidence:
        evidence.append(_text(entity.get("evidence")))

    card = {
        "id": entity.get("id"),
        "name": name,
        "aliases": list(entity.get("aliases") or raw.get("aliases") or []),
        "tier": tier,
        "role": _text(raw.get("role")) or ("supporting" if tier == "major" else "minor"),
        "age_look": age_look,
        "gender_presentation": _text(raw.get("gender_presentation"))
        or (_text(seed.get("gender_presentation")) if seed else "unspecified"),
        "appearance": {
            "face": face,
            "hair": hair,
            "body": body,
            "distinctive_marks": marks,
        },
        "wardrobe": {
            "default": wardrobe_default,
            "alternate": _str_list(wardrobe.get("alternate")),
            "colors": colors,
        },
        "temperament": _str_list(raw.get("temperament"))
        or (["内敛", "坚定"] if tier == "major" else []),
        "signature_actions": _str_list(raw.get("signature_actions")),
        "voice": {
            "timbre": timbre,
            "pace": _text(voice.get("pace")) or ("中速" if tier == "major" else ""),
            "pitch": _text(voice.get("pitch")) or ("中" if tier == "major" else ""),
            "speech_habits": _str_list(voice.get("speech_habits")),
        },
        "consistency_anchors": _str_list(raw.get("consistency_anchors"))
        or (
            [wardrobe_default, hair, f"{name}面部特征"]
            if tier == "major" and wardrobe_default
            else []
        ),
        "evidence": evidence,
        "inferred_fields": inferred,
        "prompt_zh": prompt,
        "brief": brief,
    }
    return card


def age_look_default(raw: dict) -> str:
    """Deprecated shared default — prefer seed_character_look. Kept for callers."""
    return _text(raw.get("age_look")) or "十七至二十岁年轻面相"


def ensure_location_card(entity: dict, raw: dict | None, *, tier: str) -> dict[str, Any]:
    raw = raw or {}
    name = _text(entity.get("name") or raw.get("name"))
    palette = _str_list(raw.get("palette")) or (
        ["\u9752\u7070", "\u6c34\u58a8", "\u7c73\u767d"] if tier == "major" else []
    )
    materials = _str_list(raw.get("materials")) or (
        ["\u9752\u77f3", "\u6728\u6784", "\u6c5f\u96fe"] if tier == "major" else []
    )
    era = _text(raw.get("era_mood")) or (
        "\u56fd\u98ce\u53e4\u9547\u6c5f\u6e56\u6c1b\u56f4" if tier == "major" else ""
    )
    establishing = _text(raw.get("establishing_shot")) or (
        f"\u8fdc\u666f\u5efa\u7acb\uff1a{name}\u7f6e\u4e8e\u6c5f\u96fe\u4e4b\u4e2d"
        if tier == "major"
        else ""
    )
    prompt = _text(raw.get("prompt_zh")) or (
        f"{name}\uff0c{era}\uff0c\u8272\u5f69{'/'.join(palette)}\uff0c"
        f"\u6750\u8d28{'/'.join(materials)}\uff0c\u56fd\u98ce\u573a\u666f"
        if tier == "major"
        else name
    )
    inferred = _str_list(raw.get("inferred_fields"))
    if tier == "major" and not raw.get("prompt_zh") and "prompt_zh" not in inferred:
        inferred.append("prompt_zh")
    return {
        "id": entity.get("id"),
        "name": name,
        "aliases": list(entity.get("aliases") or []),
        "tier": tier,
        "era_mood": era,
        "time_of_day_default": _text(raw.get("time_of_day_default"))
        or ("\u6e05\u6668\u6216\u9ec4\u660f" if tier == "major" else ""),
        "weather_default": _text(raw.get("weather_default"))
        or ("\u8584\u96fe" if tier == "major" else ""),
        "palette": palette,
        "materials": materials,
        "camera_grammar": _text(raw.get("camera_grammar"))
        or ("\u5e7f\u89d2\u5efa\u7acb + \u4e2d\u666f\u4eba\u7269" if tier == "major" else ""),
        "establishing_shot": establishing,
        "evidence": _str_list(raw.get("evidence")),
        "inferred_fields": inferred,
        "prompt_zh": prompt,
        "brief": _text(raw.get("brief")) or f"{name}\uff1a{era or '\u573a\u666f'}",
    }


def ensure_prop_card(entity: dict, raw: dict | None, *, tier: str) -> dict[str, Any]:
    raw = raw or {}
    name = _text(entity.get("name") or raw.get("name"))
    material = _text(raw.get("material")) or (
        "\u7389\u77f3/\u91d1\u5c5e/\u6728\u8d28" if tier == "major" else ""
    )
    closeup = _text(raw.get("closeup_notes")) or (
        f"{name}\u7eb9\u6837\u4e0e\u5149\u6cfd\u7279\u5199" if tier == "major" else ""
    )
    prompt = _text(raw.get("prompt_zh")) or (
        f"{name}\uff0c{material}\uff0c{closeup}\uff0c\u56fd\u98ce\u9053\u5177\u7279\u5199"
        if tier == "major"
        else name
    )
    inferred = _str_list(raw.get("inferred_fields"))
    if tier == "major" and not raw.get("prompt_zh") and "prompt_zh" not in inferred:
        inferred.append("prompt_zh")
    return {
        "id": entity.get("id"),
        "name": name,
        "aliases": list(entity.get("aliases") or []),
        "tier": tier,
        "scale": _text(raw.get("scale")) or ("\u638c\u4e2d\u7269" if tier == "major" else ""),
        "material": material,
        "motifs": _str_list(raw.get("motifs")),
        "closeup_notes": closeup,
        "symbolism": _text(raw.get("symbolism")),
        "evidence": _str_list(raw.get("evidence")),
        "inferred_fields": inferred,
        "prompt_zh": prompt,
        "brief": _text(raw.get("brief")) or f"{name}\uff1a{material or '\u9053\u5177'}",
    }


def ensure_faction_card(entity: dict, raw: dict | None, *, tier: str) -> dict[str, Any]:
    raw = raw or {}
    name = _text(entity.get("name") or raw.get("name"))
    palette = _str_list(raw.get("uniform_palette")) or (
        ["\u58a8\u9ed1", "\u6697\u91d1"] if tier == "major" else []
    )
    prompt = _text(raw.get("prompt_zh")) or (
        f"{name}\uff0c\u5fbd\u8bb0\u4e0e\u7edf\u4e00\u8272\u7cfb{'/'.join(palette)}\uff0c\u56fd\u98ce\u52bf\u529b"
        if tier == "major"
        else name
    )
    inferred = _str_list(raw.get("inferred_fields"))
    if tier == "major" and not raw.get("prompt_zh") and "prompt_zh" not in inferred:
        inferred.append("prompt_zh")
    return {
        "id": entity.get("id"),
        "name": name,
        "aliases": list(entity.get("aliases") or []),
        "tier": tier,
        "goal": _text(raw.get("goal"))
        or ("\u7ef4\u62a4/\u4e89\u593a\u5730\u65b9\u5229\u76ca" if tier == "major" else ""),
        "emblem": _text(raw.get("emblem")),
        "uniform_palette": palette,
        "behavior_rules": _str_list(raw.get("behavior_rules")),
        "visual_signature": _text(raw.get("visual_signature"))
        or ("\u540c\u8272\u7cfb\u670d\u9970" if tier == "major" else ""),
        "evidence": _str_list(raw.get("evidence")),
        "inferred_fields": inferred,
        "prompt_zh": prompt,
        "brief": _text(raw.get("brief")) or name,
    }


def ensure_event_beat(event: dict, raw: dict | None, character_names: list[str]) -> dict:
    raw = raw or {}
    summary = _text(event.get("summary") or raw.get("summary"))
    cast = _str_list(raw.get("cast"))
    if not cast:
        cast = [n for n in character_names if n and n in summary][:4]
    visual = _text(raw.get("visual_beat")) or summary
    camera = _text(raw.get("camera_hint")) or "\u4e2d\u666f\uff0c\u7a33\u6b65\u8ddf\u62cd"
    out = dict(event)
    out.update(
        {
            "summary": summary,
            "cast": cast,
            "location_id": raw.get("location_id") or event.get("location_id"),
            "props": _str_list(raw.get("props") or event.get("props")),
            "dramatic_beat": _text(raw.get("dramatic_beat")) or "turn",
            "emotion": _text(raw.get("emotion")) or "\u5f20\u529b",
            "visual_beat": visual,
            "camera_hint": camera,
            "duration_hint_sec": int(raw.get("duration_hint_sec") or event.get("duration_hint_sec") or 4),
        }
    )
    return out


def index_llm_items(items: Any) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if name:
            out[name] = item
        eid = _text(item.get("id"))
        if eid:
            out[eid] = item
    return out
