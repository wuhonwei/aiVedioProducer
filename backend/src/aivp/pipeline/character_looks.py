"""Per-character look seeds and hard distinctness checks for major cards."""
from __future__ import annotations

import hashlib
import re
from typing import Any

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r'[，。！？、；：:“”"\'（）()【】\[\]…—\-·,.]+')

_HAIR_POOL = (
    "黑色短发利落齐耳",
    "黑色半长发束起",
    "青丝半挽用布带",
    "灰白短发稀疏",
    "黑发用布条束起略乱",
    "洗净油亮的黑色中长发",
)
_FACE_SHAPE_POOL = ("鹅蛋脸", "国字脸", "圆脸", "长脸", "方圆脸", "瘦长脸")
_EYES_POOL = (
    "狭长杏眼",
    "圆润大眼",
    "细长凤眼",
    "深邃单眼皮",
    "温和桃花眼",
    "锐利丹凤眼",
)
_NOSE_POOL = ("高挺鼻梁", "小巧直鼻", "宽厚鼻翼", "略塌鼻梁", "挺直鼻梁", "短圆鼻")
_BROW_POOL = ("浓眉", "细长眉", "剑眉", "淡眉", "粗平眉", "弯眉")
_MOUTH_POOL = ("薄唇紧抿", "厚唇微翘", "小嘴", "宽嘴角", "唇线分明", "嘴角常带笑意")
_BODY_POOL = ("偏瘦精干", "中等匀称", "结实精壮", "纤细柔韧", "敦实敦厚", "高挑修长")
_HEIGHT_POOL = (
    "身高约一六五",
    "身高约一七〇",
    "身高约一七五",
    "身高约一八〇",
    "身高约一六〇",
    "身高约一五五",
)
_LIMBS_POOL = ("四肢修长", "手脚偏大有力", "四肢匀称", "臂膀结实", "纤细手臂", "腿长比例好")
_WEIGHT_POOL = ("体重偏轻", "体重适中", "偏壮实", "略丰腴", "清瘦见骨", "结实不胖")
_WARDROBE_POOL = (
    "洗白短打劲装",
    "靛青罩衫与束腰",
    "浅褐粗布长衫",
    "墨色短袍",
    "月白交领中衣",
    "深蓝行囊式披风短衫",
)
_WARDROBE_EXTRA = (
    "青灰布衣与半旧蓝布包袱",
    "粗布家常衣衫",
    "旧布短褐与斗笠意象",
    "深色官服长袍",
    "紧身黑衣劲装",
    "月白或藕荷交领长裙",
    "土黄短褐束袖",
    "绛色交领夹袄",
    "灰白苎麻长袍",
    "墨绿劲装束带",
    "米白短打与布履",
    "玄青直裰",
)
_WARDROBE_MODIFIERS = (
    "略旧",
    "洗净新浆",
    "带风雨痕",
    "袖口补丁",
    "腰系草绳",
    "外罩薄氅",
    "衣角磨白",
    "领口滚边",
)
_AGE_POOL = (
    "十七至二十岁年轻面相",
    "二十出头青年面相",
    "而立前后成熟面相",
    "中年沉稳面相",
)

_FEM_MARKERS = ("婆", "奶", "姥", "妪", "卿", "娘", "姝", "婉", "小姐", "夫人", "姑娘", "阿姨", "她")
_MASC_MARKERS = (
    "公子",
    "少爷",
    "郎君",
    "兄",
    "哥",
    "汉子",
    "伯",
    "翁",
    "爷们",
    "书生",
    "侠客",
    "少年",
    "他",
    "官人",
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
    for ev in entity.get("evidence_list") or []:
        if isinstance(ev, dict):
            parts.append(_text(ev.get("text") or ev.get("evidence")))
        else:
            parts.append(_text(ev))
    return "".join(parts)


def _name_slot(name: str, size: int) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(size, 1)


def gender_zh(gender_presentation: str) -> str:
    g = (gender_presentation or "").strip().lower()
    if g in {"feminine", "female", "woman", "女", "女性"}:
        return "女性"
    if g in {"masculine", "male", "man", "男", "男性"}:
        return "男性"
    return "性别未明示"


def compose_character_prompt_zh(
    *,
    name: str,
    gender_presentation: str,
    age_look: str,
    appearance: dict[str, Any],
    wardrobe_default: str,
) -> str:
    """Force full look dimensions into the string used by t2i / sheets."""
    app = appearance if isinstance(appearance, dict) else {}
    parts = [
        name.strip(),
        gender_zh(gender_presentation),
        _text(age_look) or "年龄未明示",
        _text(app.get("body")) or "中等身材",
        _text(app.get("height")) or "身高适中",
        _text(app.get("limbs")) or "四肢匀称",
        _text(app.get("weight")) or "体重适中",
        _text(app.get("face_shape")) or "脸型普通",
        _text(app.get("eyes")) or "双眼有神",
        _text(app.get("nose")) or "鼻梁端正",
        _text(app.get("eyebrows")) or "眉形自然",
        _text(app.get("mouth")) or "唇形自然",
        _text(app.get("hair")) or "黑发",
        f"身着{_text(wardrobe_default) or '常服'}",
    ]
    marks = _text(app.get("distinctive_marks"))
    if marks:
        parts.append(f"特征：{marks}")
    # Keep a compact face summary if present and not redundant
    face_summary = _text(app.get("face"))
    if face_summary and face_summary not in "，".join(parts):
        parts.insert(7, face_summary)
    parts.append("国风动画角色定妆")
    return "，".join(p for p in parts if p)


def seed_character_look(entity: dict) -> dict[str, Any]:
    """Build a per-entity look seed from evidence / aliases / stable name hash."""
    name = _text(entity.get("name") or entity.get("canonical_name"))
    blob = _blob(entity)
    aliases = " ".join(_text(a) for a in (entity.get("aliases") or []))
    signal = blob + aliases
    key = name or "x"

    age_look = _AGE_POOL[_name_slot(key, len(_AGE_POOL))]
    hair = _HAIR_POOL[_name_slot(key + ":h", len(_HAIR_POOL))]
    face_shape = _FACE_SHAPE_POOL[_name_slot(key + ":fs", len(_FACE_SHAPE_POOL))]
    eyes = _EYES_POOL[_name_slot(key + ":e", len(_EYES_POOL))]
    nose = _NOSE_POOL[_name_slot(key + ":n", len(_NOSE_POOL))]
    eyebrows = _BROW_POOL[_name_slot(key + ":b", len(_BROW_POOL))]
    mouth = _MOUTH_POOL[_name_slot(key + ":m", len(_MOUTH_POOL))]
    body = _BODY_POOL[_name_slot(key + ":bd", len(_BODY_POOL))]
    height = _HEIGHT_POOL[_name_slot(key + ":ht", len(_HEIGHT_POOL))]
    limbs = _LIMBS_POOL[_name_slot(key + ":lm", len(_LIMBS_POOL))]
    weight = _WEIGHT_POOL[_name_slot(key + ":wt", len(_WEIGHT_POOL))]
    wardrobe = _WARDROBE_POOL[_name_slot(key + ":w", len(_WARDROBE_POOL))]
    colors = ["青灰", "米白"]
    marks = ""
    gender = "unspecified"

    if any(k in signal for k in ("婆", "奶", "姥", "白发", "苍苍", "花白", "老太", "老妪")):
        age_look = "花甲前后老年面相"
        hair = "白发或花白发髻盘起"
        face_shape = "圆润多皱脸型"
        eyes = "温和细眼"
        eyebrows = "花白淡眉"
        mouth = "抿唇带笑"
        body = "略佝偻瘦小"
        height = "身高约一五〇"
        limbs = "手脚偏细"
        weight = "体重偏轻"
        wardrobe = "粗布家常衣衫"
        colors = ["米褐", "灰白"]
        if any(k in signal for k in ("婆", "奶", "姥", "妪")):
            gender = "feminine"
    elif any(k in signal for k in ("老", "翁", "老伯", "伯")) or "陈老伯" in signal:
        age_look = "五十开外沧桑面相"
        hair = "花白短发或束髻"
        face_shape = "长方沧桑脸"
        eyes = "深陷细眼"
        eyebrows = "浓眉花白"
        mouth = "唇线干裂"
        body = "瘦硬结实"
        height = "身高约一六八"
        limbs = "关节粗大"
        weight = "清瘦见骨"
        wardrobe = "旧布短褐与斗笠意象"
        colors = ["土褐", "灰"]
        gender = "masculine"

    if any(k in signal for k in ("大人", "知县", "官服", "衙役", "乌纱", "官袍")):
        age_look = "中年吏员面相"
        hair = "官帽下黑色束发"
        face_shape = "方正国字脸"
        eyes = "威严细长眼"
        eyebrows = "浓剑眉"
        mouth = "薄唇紧抿"
        body = "端正体态略丰"
        height = "身高约一七二"
        limbs = "四肢匀称"
        weight = "略丰腴"
        wardrobe = "深色官服长袍"
        colors = ["墨青", "朱红滚边"]
        gender = "masculine"

    if any(k in signal for k in ("黑衣", "蒙面", "刺客", "夜行")):
        age_look = "青壮年隐匿面相"
        hair = "黑巾束发或罩面"
        face_shape = "瘦削长脸"
        eyes = "冷峻细眼"
        eyebrows = "浓眉"
        mouth = "薄唇"
        body = "精干矫健"
        height = "身高约一七五"
        limbs = "臂膀结实"
        weight = "结实不胖"
        wardrobe = "紧身黑衣劲装"
        colors = ["黑", "深灰"]
        marks = "面巾或蒙面" if "蒙面" in signal or "黑衣" in signal else marks
        gender = "masculine" if gender == "unspecified" else gender

    if any(k in signal for k in ("包袱", "蓝布", "行囊", "赶路")):
        wardrobe = "青灰布衣与半旧蓝布包袱"
        colors = ["青灰", "蓝"]
        marks = (marks + "；半旧蓝布包袱").strip("；") if "包袱" in signal or "蓝布" in signal else marks
        if "年轻" not in age_look and "老" not in age_look and "吏" not in age_look:
            age_look = "十七至二十二岁行旅青年面相"
            hair = "黑色短打利落短发"
            body = "偏瘦精干"
            height = "身高约一七五"
            limbs = "四肢修长"
            weight = "体重偏轻"
        if gender == "unspecified":
            gender = "masculine"

    if gender == "unspecified" and any(k in name or k in signal for k in _FEM_MARKERS):
        if "老" not in age_look:
            age_look = "十六至二十岁少女面相"
            hair = "青丝半长发半挽步摇或布带"
            face_shape = "鹅蛋脸"
            eyes = "清丽杏眼"
            eyebrows = "细弯眉"
            mouth = "小嘴"
            body = "纤细柔韧"
            height = "身高约一六〇"
            limbs = "纤细手臂"
            weight = "体重偏轻"
            wardrobe = "月白或藕荷交领长裙"
            colors = ["月白", "藕荷"]
        gender = "feminine"

    if gender == "unspecified" and any(k in name or k in signal for k in _MASC_MARKERS):
        gender = "masculine"

    # Guofeng models bias female — default unspecified majors to male for t2i lock.
    if gender == "unspecified":
        gender = "masculine"

    if not marks and "蓝布包袱" in signal:
        marks = "半旧蓝布包袱"

    face = f"{face_shape}，{eyes}，{nose}，{eyebrows}，{mouth}"
    appearance = {
        "face": face,
        "face_shape": face_shape,
        "eyes": eyes,
        "nose": nose,
        "eyebrows": eyebrows,
        "mouth": mouth,
        "hair": hair,
        "body": body,
        "height": height,
        "limbs": limbs,
        "weight": weight,
        "distinctive_marks": marks,
    }
    prompt = compose_character_prompt_zh(
        name=name,
        gender_presentation=gender,
        age_look=age_look,
        appearance=appearance,
        wardrobe_default=wardrobe,
    )
    return {
        "age_look": age_look,
        "gender_presentation": gender,
        "appearance": appearance,
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
            gender_zh(_text(card.get("gender_presentation"))),
            _text(card.get("age_look")),
            _text(appearance.get("face_shape")) or _text(appearance.get("face")),
            _text(appearance.get("eyes")),
            _text(appearance.get("hair")),
            _text(appearance.get("body")),
            _text(appearance.get("height")),
            _text(wardrobe.get("default")),
            prompt,
        ]
    )
    s = _WS.sub("", raw).lower()
    s = _PUNCT.sub("", s)
    return s


def normalize_wardrobe(value: Any) -> str:
    """Collapse wardrobe strings for equality checks."""
    s = _WS.sub("", _text(value)).lower()
    s = _PUNCT.sub("", s)
    if s.startswith("身着"):
        s = s[2:]
    return s


def _wardrobe_candidates() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for w in (*_WARDROBE_POOL, *_WARDROBE_EXTRA):
        key = normalize_wardrobe(w)
        if key and key not in seen:
            seen.add(key)
            out.append(w)
    return out


def _apply_wardrobe(card: dict, wardrobe_default: str) -> None:
    wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
    colors = list(wardrobe.get("colors") or [])
    card["wardrobe"] = {
        "default": wardrobe_default,
        "alternate": list(wardrobe.get("alternate") or []),
        "colors": colors,
    }
    appearance = card.get("appearance") if isinstance(card.get("appearance"), dict) else {}
    card["prompt_zh"] = compose_character_prompt_zh(
        name=_text(card.get("name")),
        gender_presentation=_text(card.get("gender_presentation")),
        age_look=_text(card.get("age_look")),
        appearance=appearance,
        wardrobe_default=wardrobe_default,
    )


def _next_unique_wardrobe(taken: set[str], *, name: str, round_i: int) -> str:
    for cand in _wardrobe_candidates():
        key = normalize_wardrobe(cand)
        if key and key not in taken:
            return cand
    # Exhausted pool — synthesize until unique.
    base = _wardrobe_candidates()[_name_slot(name or "x", len(_wardrobe_candidates()))]
    n = 0
    while True:
        mod = _WARDROBE_MODIFIERS[(round_i + n) % len(_WARDROBE_MODIFIERS)]
        cand = f"{base}（{mod}·{n + 1}）" if n else f"{base}（{mod}）"
        key = normalize_wardrobe(cand)
        if key and key not in taken:
            return cand
        n += 1


def repair_major_wardrobe_collisions(characters: list[dict]) -> list[str]:
    """Keep rewriting colliding major wardrobes until all defaults are unique.

    First occurrence of a wardrobe is kept; later majors are reassigned from
    unused pool entries, then synthetic variants. Always terminates.
    """
    notes: list[str] = []
    round_i = 0
    while True:
        majors = [c for c in characters if (c.get("tier") or "") == "major"]
        if len(majors) <= 1:
            return notes
        owners: dict[str, str] = {}
        collisions: list[dict] = []
        for card in majors:
            wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
            key = normalize_wardrobe(wardrobe.get("default"))
            if not key:
                # Empty wardrobe is handled by assert; skip repair ownership.
                continue
            if key in owners:
                collisions.append(card)
            else:
                owners[key] = _text(card.get("name")) or "?"
        if not collisions:
            return notes
        taken = set(owners.keys())
        for card in collisions:
            old = _text((card.get("wardrobe") or {}).get("default"))
            name = _text(card.get("name")) or "?"
            new = _next_unique_wardrobe(taken, name=name, round_i=round_i)
            _apply_wardrobe(card, new)
            taken.add(normalize_wardrobe(new))
            notes.append(f"wardrobe_collision_repaired:{name}:{old}->{new}")
        round_i += 1


def assert_major_characters_distinct(characters: list[dict]) -> None:
    """Raise ValueError if any major pair collides or lacks required look fields."""
    majors = [c for c in characters if (c.get("tier") or "") == "major"]
    if not majors:
        return
    required_app = (
        "hair",
        "body",
        "height",
        "limbs",
        "weight",
        "face_shape",
        "eyes",
        "nose",
        "eyebrows",
        "mouth",
    )
    for card in majors:
        name = _text(card.get("name")) or "?"
        prompt = _text(card.get("prompt_zh"))
        if not prompt:
            raise ValueError(f"enrich_distinct_characters_failed:empty_prompt:{name}")
        gzh = gender_zh(_text(card.get("gender_presentation")))
        if gzh == "性别未明示" or gzh not in prompt:
            raise ValueError(f"enrich_distinct_characters_failed:missing_gender:{name}")
        appearance = card.get("appearance") if isinstance(card.get("appearance"), dict) else {}
        wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
        if not _text(wardrobe.get("default")):
            raise ValueError(f"enrich_distinct_characters_failed:empty_wardrobe:{name}")
        for key in required_app:
            if not _text(appearance.get(key)):
                raise ValueError(f"enrich_distinct_characters_failed:empty_{key}:{name}")

    wardrobe_seen: dict[str, str] = {}
    for card in majors:
        name = _text(card.get("name")) or "?"
        wardrobe = card.get("wardrobe") if isinstance(card.get("wardrobe"), dict) else {}
        wkey = normalize_wardrobe(wardrobe.get("default"))
        if wkey in wardrobe_seen:
            other = wardrobe_seen[wkey]
            raise ValueError(
                f"enrich_distinct_characters_failed:wardrobe_collision:{other}|{name}:{wkey[:80]}"
            )
        wardrobe_seen[wkey] = name

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
