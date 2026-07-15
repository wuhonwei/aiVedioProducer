"""Per-character look seeds and hard distinctness checks for major cards."""
from __future__ import annotations

import hashlib
import re
from typing import Any

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r'[，。！？、；：:“”"\'（）()【】\[\]…—\-·,.]+')

# Stable fallback pools when evidence is thin — indexed by name hash.
_HAIR_POOL = (
    "黑发束发",
    "青丝半挽",
    "短打利落短发",
    "灰白发簪固定",
    "乱发用布条束起",
    "洗净油亮的黑发",
)
_FACE_POOL = (
    "清瘦英气面容",
    "圆润和气脸庞",
    "冷硬棱角面相",
    "苍白细眉面容",
    "宽额沉稳面容",
    "眼窝略深的锐利面容",
)
_WARDROBE_POOL = (
    "洗白短打劲装",
    "靛青罩衫与束腰",
    "浅褐粗布长衫",
    "墨色短袍",
    "月白交领中衣",
    "深蓝行囊式披风短衫",
)
_AGE_POOL = (
    "十七至二十岁年轻面相",
    "二十出头青年面相",
    "而立前后成熟面相",
    "中年沉稳面相",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(v) for v in value if _text(v)).strip()
    return str(value).strip()


def _blob(entity: dict) -> str:
    parts = [
        _text(entity.get("name")),
        _text(entity.get("canonical_name")),
        " ".join(_text(a) for a in (entity.get("aliases") or [])),
        _text(entity.get("evidence")),
    ]
    # collect evidence list if present
    for ev in entity.get("evidence_list") or []:
        if isinstance(ev, dict):
            parts.append(_text(ev.get("text") or ev.get("evidence")))
        else:
            parts.append(_text(ev))
    return "".join(parts)


def _name_slot(name: str, size: int) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(size, 1)


def seed_character_look(entity: dict) -> dict[str, Any]:
    """Build a per-entity look seed from evidence / aliases / stable name hash."""
    name = _text(entity.get("name") or entity.get("canonical_name"))
    blob = _blob(entity)
    aliases = " ".join(_text(a) for a in (entity.get("aliases") or []))
    signal = blob + aliases

    age_look = _AGE_POOL[_name_slot(name or "x", len(_AGE_POOL))]
    hair = _HAIR_POOL[_name_slot((name or "x") + ":h", len(_HAIR_POOL))]
    face = _FACE_POOL[_name_slot((name or "x") + ":f", len(_FACE_POOL))]
    body = "中等体型"
    wardrobe = _WARDROBE_POOL[_name_slot((name or "x") + ":w", len(_WARDROBE_POOL))]
    colors = ["青灰", "米白"]
    marks = ""
    gender = "unspecified"

    # Elderly
    if any(k in signal for k in ("婆", "奶", "姥", "白发", "苍苍", "花白", "老太", "老妪")):
        age_look = "花甲前后老年面相"
        hair = "白发或花白发髻"
        face = "慈和多皱面容，眼神温和"
        wardrobe = "粗布家常衣衫"
        colors = ["米褐", "灰白"]
        gender = "feminine" if any(k in signal for k in ("婆", "奶", "姥", "妪")) else gender
    # Elder male honorifics
    elif any(k in signal for k in ("老", "翁", "老伯", "伯")) or "陈老伯" in signal:
        age_look = "五十开外沧桑面相"
        hair = "花白短发或束髻"
        face = "皱纹深刻的沉稳面容"
        wardrobe = "旧布短褐与斗笠意象"
        colors = ["土褐", "灰"]
    # Official
    if any(k in signal for k in ("大人", "知县", "官服", "衙役", "乌纱", "官袍")):
        age_look = "中年吏员面相"
        hair = "官帽下束发"
        face = "威严端正面容"
        wardrobe = "深色官服长袍"
        colors = ["墨青", "朱红滚边"]
        body = "略丰或端正体态"
    # Assassin / black clothes
    if any(k in signal for k in ("黑衣", "蒙面", "刺客", "夜行")):
        age_look = "青壮年隐匿面相"
        hair = "黑巾束发或罩面"
        face = "半遮面的冷峻面容"
        wardrobe = "紧身黑衣劲装"
        colors = ["黑", "深灰"]
        marks = "面巾或蒙面" if "蒙面" in signal or "黑衣" in signal else marks
    # Traveler / pack
    if any(k in signal for k in ("包袱", "蓝布", "行囊", "赶路")):
        wardrobe = "青灰布衣与半旧蓝布包袱"
        colors = ["青灰", "蓝"]
        marks = (marks + "；半旧蓝布包袱").strip("；") if "包袱" in signal or "蓝布" in signal else marks
        if "年轻" not in age_look and "老" not in age_look and "吏" not in age_look:
            age_look = "十七至二十二岁行旅青年面相"
    # Feminine young (weak heuristic)
    if gender == "unspecified" and any(
        k in name for k in ("卿", "娘", "姝", "婉", "青青", "小姐")
    ):
        if "老" not in age_look:
            age_look = "十六至二十岁少女面相"
            hair = "青丝半挽步摇或布带"
            face = "清丽柔和面容"
            wardrobe = "月白或藕荷交领长裙"
            colors = ["月白", "藕荷"]
            gender = "feminine"

    if not marks and "蓝布包袱" in signal:
        marks = "半旧蓝布包袱"

    prompt = (
        f"{name}，{age_look}，{hair}，{face}，身着{wardrobe}"
        + (f"，特征：{marks}" if marks else "")
        + "，国风动画角色定妆"
    )
    return {
        "age_look": age_look,
        "gender_presentation": gender,
        "appearance": {
            "face": face,
            "hair": hair,
            "body": body,
            "distinctive_marks": marks,
        },
        "wardrobe": {
            "default": wardrobe,
            "alternate": [],
            "colors": colors,
        },
        "prompt_zh": prompt,
        "evidence": [_text(entity.get("evidence"))] if _text(entity.get("evidence")) else [],
    }


def _strip_leading_name(prompt: str, name: str) -> str:
    p = prompt.strip()
    n = name.strip()
    if n and p.startswith(n):
        p = p[len(n) :].lstrip("，,：: ")
    return p


def look_signature(card: dict) -> str:
    """Normalized visual signature for collision detection."""
    name = _text(card.get("name"))
    appearance = card.get("appearance") if isinstance(card.get("appearance"), dict) else {}
    wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
    prompt = _strip_leading_name(_text(card.get("prompt_zh")), name)
    raw = "｜".join(
        [
            _text(card.get("age_look")),
            _text(appearance.get("face")),
            _text(appearance.get("hair")),
            _text(wardrobe.get("default")),
            prompt,
        ]
    )
    s = _WS.sub("", raw).lower()
    s = _PUNCT.sub("", s)
    return s


def assert_major_characters_distinct(characters: list[dict]) -> None:
    """Raise ValueError if any major pair collides or lacks required look fields."""
    majors = [c for c in characters if (c.get("tier") or "") == "major"]
    if not majors:
        return
    for card in majors:
        name = _text(card.get("name")) or "?"
        if not _text(card.get("prompt_zh")):
            raise ValueError(f"enrich_distinct_characters_failed:empty_prompt:{name}")
        appearance = card.get("appearance") if isinstance(card.get("appearance"), dict) else {}
        wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
        if not (_text(appearance.get("face")) or _text(wardrobe.get("default"))):
            raise ValueError(f"enrich_distinct_characters_failed:empty_look:{name}")

    seen: dict[str, str] = {}
    for card in majors:
        name = _text(card.get("name")) or "?"
        sig = look_signature(card)
        if not sig:
            raise ValueError(f"enrich_distinct_characters_failed:empty_signature:{name}")
        if sig in seen:
            other = seen[sig]
            raise ValueError(
                f"enrich_distinct_characters_failed:collision:{other}|{name}:{sig[:80]}"
            )
        seen[sig] = name
