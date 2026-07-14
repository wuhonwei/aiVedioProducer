from __future__ import annotations

from typing import Any


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
    appearance = raw.get("appearance") if isinstance(raw.get("appearance"), dict) else {}
    wardrobe = raw.get("wardrobe") if isinstance(raw.get("wardrobe"), dict) else {}
    voice = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}

    face = _text(appearance.get("face")) or (
        "\u6e05\u4fca\u56fd\u98ce\u9762\u5bb9\uff0c\u7709\u773c\u6709\u795e"
        if tier == "major"
        else ""
    )
    hair = _text(appearance.get("hair")) or (
        "\u9ed1\u53d1\u675f\u53d1\u6216\u534a\u675f" if tier == "major" else ""
    )
    body = _text(appearance.get("body")) or (
        "\u4e2d\u7b49\u4f53\u578b" if tier == "major" else ""
    )
    marks = _text(appearance.get("distinctive_marks"))
    wardrobe_default = _text(wardrobe.get("default")) or (
        "\u9752\u7070\u8272\u5e03\u8863\u957f\u886b" if tier == "major" else ""
    )
    colors = _str_list(wardrobe.get("colors")) or (
        ["\u9752\u7070", "\u7c73\u767d"] if tier == "major" else []
    )
    timbre = _text(voice.get("timbre")) or (
        "\u4e2d\u9752\u5e74\u6e05\u67d4\u7537\u58f0" if tier == "major" else ""
    )
    prompt = _text(raw.get("prompt_zh"))
    if not prompt and tier == "major":
        prompt = (
            f"{name}\uff0c{age_look_default(raw)}\uff0c{hair}\uff0c{face}\uff0c"
            f"\u8eab\u7740{wardrobe_default}\uff0c\u56fd\u98ce\u52a8\u753b\u89d2\u8272\u5b9a\u5986"
        )
    fallback_tag = wardrobe_default or face or "\u914d\u89d2"
    brief = _text(raw.get("brief")) or ("%s\uff1a%s" % (name, fallback_tag))
    inferred = _str_list(raw.get("inferred_fields"))
    for field, filled in [
        ("appearance.face", face and not _text((appearance or {}).get("face"))),
        ("wardrobe.default", wardrobe_default and not _text((wardrobe or {}).get("default"))),
        ("voice.timbre", timbre and not _text((voice or {}).get("timbre"))),
        ("prompt_zh", prompt and not _text(raw.get("prompt_zh"))),
    ]:
        if filled and field not in inferred:
            inferred.append(field)

    card = {
        "id": entity.get("id"),
        "name": name,
        "aliases": list(entity.get("aliases") or raw.get("aliases") or []),
        "tier": tier,
        "role": _text(raw.get("role")) or ("supporting" if tier == "major" else "minor"),
        "age_look": _text(raw.get("age_look")) or age_look_default(raw),
        "gender_presentation": _text(raw.get("gender_presentation")) or "unspecified",
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
        or (["\u5185\u655b", "\u575a\u5b9a"] if tier == "major" else []),
        "signature_actions": _str_list(raw.get("signature_actions")),
        "voice": {
            "timbre": timbre,
            "pace": _text(voice.get("pace")) or ("\u4e2d\u901f" if tier == "major" else ""),
            "pitch": _text(voice.get("pitch")) or ("\u4e2d" if tier == "major" else ""),
            "speech_habits": _str_list(voice.get("speech_habits")),
        },
        "consistency_anchors": _str_list(raw.get("consistency_anchors"))
        or (
            [wardrobe_default, hair, f"{name}\u9762\u90e8\u7279\u5f81"]
            if tier == "major" and wardrobe_default
            else []
        ),
        "evidence": _str_list(raw.get("evidence")),
        "inferred_fields": inferred,
        "prompt_zh": prompt,
        "brief": brief,
    }
    return card


def age_look_default(raw: dict) -> str:
    return _text(raw.get("age_look")) or "\u5341\u4e03\u81f3\u4e8c\u5341\u5c81\u5e74\u8f7b\u9762\u76f8"


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
