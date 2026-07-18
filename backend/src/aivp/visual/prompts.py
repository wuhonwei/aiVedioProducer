from __future__ import annotations

# Shared framing / negatives for character-focused gens (avoid empty scenery).

PROBE_FRAMING = (
    "solo, 1person, looking at viewer, upper body portrait, "
    "simple background, 人物半身特写"
)

CHARACTER_NEGATIVE = (
    "lowres, blurry, inconsistent face, bad anatomy, watermark, "
    "scenery, landscape, palace, architecture, empty, no humans, "
    "out of frame, cropped head, cropped feet, cropped legs, "
    "upper body only, portrait crop, close-up, bust shot, "
    "modern clothes, western clothes, "
    "school uniform, armor, wedding dress, costume change, different outfit, "
    "shirtless, bare chest, topless, nude, naked, open shirt, exposed midriff, "
    "multiple people, 2people, 2girls, 2boys, crowd"
)

# "turnaround sheet / character sheet" in anime priors often means multi-view plate.
TURNAROUND_MULTI_NEGATIVE = (
    "multiple people, 2people, 2girls, 2boys, 3girls, 3boys, crowd, twins, clone, "
    "character sheet, turnaround sheet, model sheet, reference sheet, "
    "multiple views, collage, split screen, grid layout, triptych, diptych, "
    "two figures, two poses, front and back together, three views in one image, "
    "mirror, reflection, extra person, duplicate character, group shot, "
    "side by side characters, paired poses"
)

SHEET_NEGATIVE = CHARACTER_NEGATIVE + ", " + TURNAROUND_MULTI_NEGATIVE

# Expressions are face-only — do NOT reuse CHARACTER_NEGATIVE (it bans close-up).
EXPRESSION_NEGATIVE = (
    "lowres, blurry, inconsistent face, bad anatomy, watermark, "
    "scenery, landscape, palace, architecture, empty, no humans, "
    "full body, entire body, head to toe, feet, legs, hands, arms, "
    "torso, chest, waist, hips, standing, walking, sitting, "
    "upper body, half body, cowboy shot, medium shot, wide shot, "
    "letterbox, pillarbox, black bars, white bars, gray bars, "
    "border, frame, empty margins, side padding, "
    "modern clothes, western clothes, "
    "school uniform, armor, wedding dress, costume change, different outfit, "
    "multiple people, 2people, 2girls, 2boys, crowd"
)

_OUTFIT_DRIFT_NEGATIVE = (
    "costume change, different outfit, outfit swap, clothing mismatch, "
    "random clothes, bare shoulders, revealing clothes, modern streetwear, "
    "hoodie, t-shirt, jeans, suit, dress suit, "
    "shirtless, bare chest, topless, nude, naked, open shirt, unbuttoned, "
    "exposed midriff, navel, nipples, cleavage, skimpy clothes, lingerie, "
    "armor, bikini, crop top, tank top, bare torso, no shirt, torn clothes"
)

# Chinese wardrobe phrases → English CLIP tokens (Guofeng SDXL is English-biased).
_WARDROBE_EN_RULES: list[tuple[str, str]] = [
    ("黑衣", "all-black clothing"),
    ("深蓝", "dark blue"),
    ("青灰", "blue-gray"),
    ("月白", "moon white"),
    ("藕荷", "pale pink"),
    ("玄色", "black"),
    ("墨色", "ink black"),
    ("朱红", "vermilion"),
    ("藏青", "navy blue"),
    ("深灰", "dark gray"),
    ("披风", "cloak cape"),
    ("斗篷", "cloak"),
    ("短衫", "short tunic"),
    ("长衫", "long robe tunic"),
    ("长袍", "long robe"),
    ("交领", "crossed-collar hanfu"),
    ("行囊", "travel-cloak style"),
    ("劲装", "martial tight outfit"),
    ("官服", "official robe"),
    ("布衣", "plain cloth robe"),
    ("粗布", "coarse homespun cloth"),
    ("家常", "everyday commoner clothes"),
    ("衣衫", "simple tunic robe"),
    ("短褐", "coarse short jacket"),
    ("绣裙", "embroidered skirt"),
    ("裙", "skirt"),
    ("腰带", "sash belt"),
    ("布带", "cloth hair tie"),
]

_COLOR_EN: dict[str, str] = {
    "黑": "black",
    "深灰": "dark gray",
    "灰": "gray",
    "白": "white",
    "米褐": "beige brown",
    "灰白": "gray white",
    "土褐": "earth brown",
    "墨青": "ink blue-black",
    "青灰": "blue-gray",
    "深蓝": "dark blue",
    "朱红": "vermilion",
    "月白": "moon white",
    "藕荷": "pale pink",
}


def wardrobe_english_tokens(outfit_zh: str, *, colors: list[str] | None = None) -> list[str]:
    """Translate key Chinese wardrobe cues into English tokens for SDXL."""
    text = (outfit_zh or "").strip()
    if not text:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for zh, en in _WARDROBE_EN_RULES:
        if zh in text and en not in seen:
            hits.append(en)
            seen.add(en)
    # Standalone 黑 in outfit text (e.g. 紧身黑衣劲装) when 黑衣 rule already hit is fine.
    if "黑" in text and "black" not in " ".join(hits):
        hits.insert(0, "black")
        seen.add("black")
    for c in colors or []:
        c = str(c).strip()
        if not c:
            continue
        if c in _COLOR_EN and _COLOR_EN[c] not in seen:
            hits.append(_COLOR_EN[c])
            seen.add(_COLOR_EN[c])
            continue
        for zh, en in _WARDROBE_EN_RULES:
            if zh in c and en not in seen:
                hits.append(en)
                seen.add(en)
    if not hits:
        return [f"wearing traditional chinese guofeng outfit inspired by {text}"]
    color_lock = ""
    joined = " ".join(hits)
    if "black" in joined or "all-black" in joined:
        color_lock = (
            "pure black clothing only, matte black fabric, no blue no cyan no teal "
            "no turquoise no green accents"
        )
    out = [
        "wearing " + " ".join(hits),
        "guofeng traditional outfit",
    ]
    # Keep martial tag only when the outfit is actually combat gear.
    if any(k in text for k in ("劲装", "短打", "夜行", "刺客")):
        out.append("guofeng martial outfit")
    if color_lock:
        out.append(color_lock)
    return out


def clothing_coverage_tokens() -> list[str]:
    return [
        "fully clothed",
        "covered chest and torso",
        "closed collar",
        "modest clothing",
        "no bare skin on torso",
        "proper historical chinese attire",
    ]


def face_concealed(profile: dict | None = None, *, text_hints: str = "", name: str = "") -> bool:
    """True when character should keep face covered (mask / veil / hood)."""
    appearance = {}
    anchors: list = []
    if isinstance(profile, dict):
        appearance = (
            profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {}
        )
        anchors = profile.get("consistency_anchors") or []
        name = name or str(profile.get("name") or "")
        text_hints = text_hints or str(profile.get("prompt_zh") or "")
    blob = " ".join(
        [
            name,
            text_hints,
            str(appearance.get("hair") or ""),
            str(appearance.get("distinctive_marks") or ""),
            " ".join(str(a) for a in anchors if a),
        ]
    )
    return any(
        k in blob
        for k in (
            "蒙面",
            "面巾",
            "罩面",
            "黑巾",
            "遮脸",
            "面纱",
            "面罩",
            "黑衣人",
            "masked",
            "face veil",
            "face covered",
        )
    )


def concealment_lock_positive(profile: dict) -> list[str]:
    if not face_concealed(profile):
        return []
    return [
        "face fully covered by black cloth mask",
        "black face veil, black head wrap, masked assassin",
        "only eyes barely visible or eyes hidden, no bare face",
        "蒙面, 面巾罩面, 黑巾遮脸",
    ]


def concealment_lock_negative(profile: dict | None = None, *, text_hints: str = "", name: str = "") -> str:
    if not face_concealed(profile, text_hints=text_hints, name=name):
        return ""
    return (
        "bare face, exposed face, full face visible, uncovered face, "
        "pretty face, detailed facial features, smiling face, lips visible, "
        "nose bridge fully visible, open face, no mask, unmasked"
    )


def wardrobe_color_negative(profile: dict) -> str:
    """Ban common Guofeng color drift when outfit is locked black/etc."""
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    default = str(wardrobe.get("default") or "")
    colors = wardrobe.get("colors") if isinstance(wardrobe.get("colors"), list) else []
    blob = default + " " + " ".join(str(c) for c in colors)
    if "黑" in blob or "玄" in blob or "墨" in blob:
        return (
            "blue clothes, cyan clothes, teal clothes, turquoise clothes, "
            "green clothes, white hanfu, colorful embroidery, bright outfit, "
            "blue robe, teal robe"
        )
    return ""


def age_appearance_english_boost(
    *,
    age_look: str = "",
    appearance: dict | None = None,
    text_hints: str = "",
    name: str = "",
) -> list[str]:
    """Force English age/hair cues early — Chinese alone loses to Guofeng youth priors."""
    band = age_band(age_look, text_hints=text_hints, name=name)
    blob = f"{age_look} {text_hints} {name}"
    app = appearance if isinstance(appearance, dict) else {}
    for key in ("hair", "face", "face_shape", "eyebrows", "body"):
        blob += f" {app.get(key) or ''}"
    tokens: list[str] = []
    if any(k in blob for k in ("白发", "花白", "鹤发", "gray", "white hair", "grey")):
        tokens.append("white gray hair, grayish white hair, aged hair color")
    if band == "elder":
        tokens.extend(
            [
                "deep wrinkles, sagging cheeks, aged skin texture",
                "elderly body proportions, slightly hunched posture ok",
            ]
        )
    elif band == "middle":
        tokens.extend(
            [
                "mature weathered skin, crow's feet, slight wrinkles",
                "grizzled or salt-and-pepper hair if described",
            ]
        )
    return tokens


def wardrobe_lock_tokens(profile: dict) -> list[str]:
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    default_outfit = str(wardrobe.get("default") or "").strip()
    colors_raw = wardrobe.get("colors") if isinstance(wardrobe.get("colors"), list) else []
    colors = [str(c).strip() for c in colors_raw if str(c).strip()]
    tokens: list[str] = []
    if default_outfit:
        tokens.extend(wardrobe_english_tokens(default_outfit, colors=colors))
        tokens.append(f"wearing {default_outfit}")
        tokens.append(f"身着{default_outfit}")
        tokens.append("same outfit, identical clothing")
        tokens.append("keep the exact described wardrobe")
    tokens.extend(clothing_coverage_tokens())
    return tokens


def normalize_gender(
    gender_presentation: str | None,
    *,
    text_hints: str = "",
) -> str:
    """Return male | female | unspecified, with light inference from Chinese look text."""
    g = (gender_presentation or "").strip().lower()
    if g in {"masculine", "male", "man", "男", "男性"}:
        return "male"
    if g in {"feminine", "female", "woman", "女", "女性"}:
        return "female"
    blob = text_hints or ""
    if any(k in blob for k in ("女性", "少女", "姑娘", "女主", "小姐", "妹妹", "姐姐", "娘")):
        return "female"
    if any(
        k in blob
        for k in ("男性", "少年", "公子", "郎君", "书生", "侠客", "少侠", "哥哥", "弟弟", "男主")
    ):
        return "male"
    if "女" in blob and "男" not in blob:
        return "female"
    if "男" in blob and "女" not in blob:
        return "male"
    return "unspecified"


def age_band(
    age_look: str | None = None,
    *,
    text_hints: str = "",
    name: str = "",
) -> str:
    """Return elder | middle | young_adult | child from Chinese/English age cues."""
    blob = f"{age_look or ''} {text_hints or ''} {name or ''}"
    # Elder first: 花甲/婆婆/老年 — never fall through to young Guofeng priors.
    if any(
        k in blob
        for k in (
            "老年",
            "老者",
            "花甲",
            "古稀",
            "耄耋",
            "六十",
            "七十",
            "八十",
            "婆婆",
            "爷爷",
            "奶奶",
            "老太",
            "老妪",
            "老汉",
            "鹤发",
            "白发苍苍",
            "elder",
            "elderly",
            "old woman",
            "old man",
            "grandmother",
            "grandfather",
        )
    ):
        return "elder"
    # 青壮年 contains 壮年 — must resolve BEFORE middle-aged 壮年.
    if any(
        k in blob
        for k in (
            "青壮年",
            "青年",
            "年轻",
            "少年感",
            "young adult",
            "youthful adult",
        )
    ):
        return "young_adult"
    # Late middle / weathered 50+: 五十开外沧桑 — not young idol face.
    if any(
        k in blob
        for k in (
            "中年",
            "壮年",
            "不惑",
            "四十",
            "五十",
            "五十开外",
            "沧桑",
            "mature",
            "middle-aged",
            "middle aged",
            "weathered",
        )
    ):
        return "middle"
    if any(k in blob for k in ("少年", "幼童", "孩童", "儿童", "child", "kid", "toddler")):
        return "child"
    return "young_adult"


def age_lock_positive(band: str, gender: str) -> str:
    if band == "elder":
        if gender == "female":
            return (
                "elderly old woman, grandmother appearance, deeply wrinkled aged face, "
                "gray white hair, sagging aged skin, old lady, aged female, not young"
            )
        if gender == "male":
            return (
                "elderly old man, weathered deeply aged face, gray white hair or beard, "
                "wrinkled skin, old gentleman, aged male, not young"
            )
        return "elderly person, wrinkled aged face, gray white hair, not young"
    if band == "middle":
        if gender == "female":
            return (
                "middle-aged woman, mature adult face, early wrinkles, "
                "not youthful, not teenage"
            )
        if gender == "male":
            return (
                "middle-aged man in his fifties, mature weathered face, "
                "graying hair, crow's feet, not youthful, not young adult idol"
            )
        return "middle-aged adult, mature weathered face, not youthful"
    if band == "child":
        return "child, young kid"
    if gender == "female":
        return "young adult woman"
    if gender == "male":
        return "young adult man"
    return "young adult"


def age_lock_negative(band: str, gender: str) -> str:
    if band == "elder":
        if gender == "female":
            return (
                "1girl, young girl, teenage girl, beautiful young woman, loli, idol face, "
                "smooth youthful skin, baby face, teen, child, glamorous young beauty, "
                "pretty anime girl, schoolgirl, black long silky hair, jet black hair, "
                "youthful makeup, red lipstick, flower hairpin glam"
            )
        if gender == "male":
            return (
                "1boy, young man, teenage boy, handsome youth, idol face, "
                "smooth youthful skin, baby face, teen, child, shota, pretty boy, "
                "jet black hair, youthful male model"
            )
        return (
            "young girl, teenage girl, young woman, beautiful youth, loli, idol face, "
            "smooth youthful skin, baby face, teen, child, kid, "
            "young man, teenage boy, handsome young idol, shota"
        )
    if band == "middle":
        if gender == "male":
            return (
                "young man, teenage boy, handsome youth, idol face, pretty boy, "
                "smooth youthful skin, baby face, teen, child, kid, shota, "
                "young adult male model"
            )
        if gender == "female":
            return (
                "young girl, teenage girl, beautiful young woman, loli, idol face, "
                "smooth youthful skin, baby face, teen, child, kid"
            )
        return (
            "teenager, teen boy, teen girl, young boy, young girl, child, kid, "
            "baby face, shota, loli, young adult idol"
        )
    if band == "child":
        return "elderly, old man, old woman, wrinkled face"
    return ""


def gender_lock_positive(
    gender: str,
    *,
    age_look: str | None = None,
    text_hints: str = "",
    name: str = "",
    view_mode: str | None = None,
) -> str:
    band = age_band(age_look, text_hints=text_hints, name=name)
    age_pos = age_lock_positive(band, gender)
    view = (view_mode or "").strip().lower()
    # Side/back: avoid "face" wording — it pulls facing-camera portraits.
    if view in {"side", "turnaround_side", "profile"}:
        if band == "elder":
            if gender == "female":
                return (
                    "solo, elderly old woman in strict side profile, "
                    "grandmother silhouette from the side, gray white hair, wrinkled skin"
                )
            if gender == "male":
                return (
                    "solo, elderly old man in strict side profile, "
                    "aged gentleman silhouette from the side, gray white hair, wrinkled skin"
                )
            return "solo, elderly person in strict side profile, gray white hair"
        if band == "middle":
            if gender == "female":
                return "solo, middle-aged woman in strict side profile, mature silhouette from the side"
            if gender == "male":
                return (
                    "solo, middle-aged man in his fifties in strict side profile, "
                    "weathered silhouette from the side, graying hair"
                )
            return "solo, middle-aged adult in strict side profile"
    if view in {"back", "turnaround_back", "rear"}:
        if band == "elder":
            if gender == "female":
                return (
                    "solo, elderly old woman from behind, back of head and body only, "
                    "gray white hair bun, no face visible"
                )
            if gender == "male":
                return (
                    "solo, elderly old man from behind, back of head and body only, "
                    "gray white hair, no face visible"
                )
            return "solo, elderly person from behind, no face visible"
        if band == "middle":
            if gender == "female":
                return "solo, middle-aged woman from behind, back of head and body only, no face visible"
            if gender == "male":
                return (
                    "solo, middle-aged man from behind, back of head and body only, "
                    "graying hair, no face visible"
                )
            return "solo, middle-aged adult from behind, no face visible"
    # Age tokens first. Avoid 1girl/1boy for elder/middle — Guofeng maps them to youth.
    concealed = face_concealed(text_hints=text_hints, name=name) or any(
        k in f"{age_look or ''} {text_hints} {name}"
        for k in ("蒙面", "面巾", "罩面", "黑衣人")
    )
    if concealed and view_mode not in {"side", "back", "turnaround_side", "turnaround_back"}:
        if gender == "male":
            return (
                "solo, 1boy, male, masked man, face covered, "
                f"{age_pos}, black cloth mask"
            )
        if gender == "female":
            return (
                "solo, 1girl, female, masked woman, face covered, "
                f"{age_pos}, black cloth mask"
            )
        return f"solo, 1person, masked figure, face covered, {age_pos}"
    if band == "elder":
        if gender == "female":
            if view in {"full_body", "candidate", "full"}:
                return (
                    f"solo, 1oldwoman, elderly woman full body standing, "
                    f"grandmother figure, gray white hair, {age_pos}"
                )
            return f"solo, 1oldwoman, elderly woman, aged female face, {age_pos}"
        if gender == "male":
            if view in {"full_body", "candidate", "full"}:
                return (
                    f"solo, 1oldman, elderly man full body standing, "
                    f"aged gentleman figure, gray white hair, {age_pos}"
                )
            return f"solo, 1oldman, elderly man, aged male face, {age_pos}"
        return f"solo, 1person, {age_pos}"
    if band == "middle":
        if gender == "female":
            return f"solo, 1woman, mature female, middle-aged woman face, {age_pos}"
        if gender == "male":
            return f"solo, 1man, mature male, middle-aged man face, {age_pos}"
        return f"solo, 1person, {age_pos}"
    if gender == "male":
        return f"1boy, solo, male, masculine face, {age_pos}"
    if gender == "female":
        return f"1girl, solo, female, feminine face, {age_pos}"
    return f"solo, 1person, {age_pos}"


def gender_lock_negative(
    gender_presentation: str | None,
    *,
    age_look: str | None = None,
    text_hints: str = "",
    name: str = "",
) -> str:
    """Extra negatives to reduce cross-gender and age drift on Guofeng priors."""
    g = normalize_gender(gender_presentation, text_hints=f"{text_hints} {name}")
    band = age_band(age_look, text_hints=text_hints, name=name)
    parts: list[str] = []
    if g == "male":
        parts.append(
            "1girl, woman, female, girl, feminine face, breasts, "
            "lipstick, long eyelashes, makeup"
        )
    elif g == "female":
        parts.append("1boy, man, male, boy, masculine face, beard, adam's apple")
    age_neg = age_lock_negative(band, g)
    if age_neg:
        parts.append(age_neg)
    return ", ".join(parts)


def character_negative_for(
    gender_presentation: str | None = None,
    *,
    age_look: str | None = None,
    text_hints: str = "",
    name: str = "",
) -> str:
    parts = [CHARACTER_NEGATIVE, _OUTFIT_DRIFT_NEGATIVE]
    extra = gender_lock_negative(
        gender_presentation, age_look=age_look, text_hints=text_hints, name=name
    )
    if extra:
        parts.append(extra)
    return ", ".join(parts)


def candidate_negative_for(profile: dict) -> str:
    name = str(profile.get("name") or "")
    look = str(profile.get("prompt_zh") or "")
    gender = normalize_gender(
        profile.get("gender_presentation"),
        text_hints=f"{look} {name}",
    )
    parts = [
        character_negative_for(
            gender,
            age_look=str(profile.get("age_look") or ""),
            text_hints=look,
            name=name,
        ),
        # Guofeng priors love elder-woman bust shots; hard-ban for candidates.
        "half body, waist up, cowboy shot, medium shot, head and shoulders, "
        "bust portrait, upper body portrait, facial close-up, tight crop, "
        "cropped at waist, missing legs, missing feet, no shoes",
    ]
    cneg = concealment_lock_negative(profile, text_hints=look, name=name)
    if cneg:
        parts.append(cneg)
    wneg = wardrobe_color_negative(profile)
    if wneg:
        parts.append(wneg)
    return ", ".join(parts)


def build_candidate_prompt(profile: dict, view: str) -> str:
    """Framing first, then gender/look/wardrobe — view/framing last as reinforcement."""
    trigger = str(profile.get("trigger") or "character_aivp").strip()
    name = str(profile.get("name") or "").strip()
    look = sanitized_look_text(profile)
    age_look = str(profile.get("age_look") or "").strip()
    gender = normalize_gender(
        profile.get("gender_presentation"),
        text_hints=f"{look} {name} {profile.get('prompt_zh') or ''}",
    )
    wardrobe_first = wardrobe_lock_tokens(profile)
    age_boost = age_appearance_english_boost(
        age_look=age_look,
        appearance=profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {},
        text_hints=look,
        name=name,
    )
    conceal = concealment_lock_positive(profile)
    framing = (
        "wide shot, full body, head to toe, feet visible, shoes visible, "
        "entire figure in frame, standing far enough to show whole body, "
        "space above head and below feet, not cropped"
    )
    parts = [
        framing,
        gender_lock_positive(
            gender,
            age_look=age_look,
            text_hints=f"{look} {name}",
            name=name,
            view_mode="full_body",
        ),
        *conceal,
        *age_boost,
        *wardrobe_first,
        trigger,
        look,
        *appearance_lock_tokens(profile),
        view,
        framing,
        "guofeng anime style, consistent character design, masterpiece",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = str(p).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return ", ".join(out)


def sheet_negative_for(
    gender_presentation: str | None = None,
    *,
    slot_key: str | None = None,
    text_hints: str = "",
    age_look: str | None = None,
    name: str = "",
    profile: dict | None = None,
) -> str:
    gender = normalize_gender(gender_presentation, text_hints=f"{text_hints} {name}")
    key = (slot_key or "").strip().lower()
    base = EXPRESSION_NEGATIVE if key.startswith("expr_") else CHARACTER_NEGATIVE
    parts = [base, TURNAROUND_MULTI_NEGATIVE, _OUTFIT_DRIFT_NEGATIVE]
    gneg = gender_lock_negative(
        gender, age_look=age_look, text_hints=text_hints, name=name
    )
    if gneg:
        parts.append(gneg)
    view = _view_lock_negative(slot_key)
    if view:
        parts.append(view)
    if profile is not None:
        cneg = concealment_lock_negative(profile, text_hints=text_hints, name=name)
        if cneg and not key.startswith("expr_"):
            parts.append(cneg)
        wneg = wardrobe_color_negative(profile)
        if wneg:
            parts.append(wneg)
    slot_neg = EXPRESSION_SLOT_NEGATIVES.get(key)
    if slot_neg:
        parts.append(slot_neg)
    return ", ".join(parts)


def appearance_lock_tokens(
    profile: dict,
    *,
    for_expression: bool = False,
    include_default_expression: bool | None = None,
) -> list[str]:
    """Stable look tokens from profile appearance / wardrobe / anchors.

    Identity (hair, face shape, outfit) is always locked.
    ``default_expression`` (e.g. 抿唇带笑) is only for candidates / calm —
    never for angry/sad/surprised sheets.
    """
    from aivp.visual.profiles import default_expression_of

    tokens: list[str] = []
    appearance = profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {}
    concealed = face_concealed(profile)
    face_keys = ("face", "face_shape", "eyes", "eyebrows", "nose", "mouth")
    skip_keys = {"mouth"} if for_expression else set()
    if include_default_expression is None:
        include_default_expression = not for_expression
    _EXPR_MOUTH_LOCK = (
        "抿唇",
        "带笑",
        "微笑",
        "浅笑",
        "笑意",
        "笑脸",
        "smile",
        "grin",
        "laugh",
    )
    for key in (
        "hair",
        "face",
        "face_shape",
        "eyes",
        "eyebrows",
        "nose",
        "mouth",
        "body",
        "height",
        "distinctive_marks",
    ):
        if key in skip_keys:
            continue
        if concealed and key in face_keys:
            # Face traits stay under the mask — don't force bare-face detail.
            continue
        val = appearance.get(key)
        if not val:
            continue
        text = str(val).strip()
        if for_expression and any(k in text.lower() or k in text for k in _EXPR_MOUTH_LOCK):
            # Keep structural face cues; strip smile-locked phrases.
            cleaned = text
            for k in ("抿唇带笑", "抿唇", "带笑", "微笑", "浅笑", "笑意"):
                cleaned = cleaned.replace(k, "")
            cleaned = cleaned.strip("，, ").strip()
            if not cleaned:
                continue
            text = cleaned
        if for_expression and key == "eyes":
            # "温和细眼" fights angry glare / wide surprised eyes.
            for k in ("温和", "柔和", "细眼"):
                text = text.replace(k, "")
            text = text.strip("，, ").strip() or "aged eyes"
        tokens.append(text)
    tokens.extend(concealment_lock_positive(profile))
    tokens.extend(wardrobe_lock_tokens(profile))
    anchors = profile.get("consistency_anchors") or []
    if isinstance(anchors, list):
        for a in anchors:
            t = str(a).strip()
            if not t or t in tokens:
                continue
            if concealed and ("面部" in t or "脸" in t):
                continue
            if for_expression and any(k in t for k in ("抿唇", "带笑", "微笑")):
                continue
            tokens.append(t)
    age = str(profile.get("age_look") or "").strip()
    if age:
        tokens.append(age)
    if include_default_expression:
        de = default_expression_of(profile)
        if de and de not in tokens:
            tokens.append(de)
    return [t for t in tokens if t]


def sanitized_look_text(
    profile: dict, look: str | None = None, *, for_expression: bool = False
) -> str:
    """For masked characters, drop bare-face trait spam from prompt_zh."""
    raw = (look if look is not None else str(profile.get("prompt_zh") or "")).strip()
    if for_expression:
        for k in ("抿唇带笑", "抿唇浅笑", "面带微笑", "浅笑", "带笑"):
            raw = raw.replace(k, "")
        raw = raw.strip("，, ").strip()
    if not face_concealed(profile):
        return raw
    name = str(profile.get("name") or "").strip()
    age = str(profile.get("age_look") or "").strip()
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    outfit = str(wardrobe.get("default") or "").strip()
    parts = [p for p in (name, age, f"身着{outfit}" if outfit else "", "蒙面罩面遮脸", "国风动画角色定妆") if p]
    return "，".join(parts) if parts else raw


def _view_lock_negative(slot_key: str | None) -> str:
    key = (slot_key or "").strip().lower()
    if key.startswith("expr_"):
        return (
            "full body, entire figure, head to toe, feet visible, legs visible, "
            "hands visible, arms visible, torso visible, shoulders down, "
            "clothing folds on body, outfit details below neck, "
            "standing pose, action pose, wide angle, "
            "half face, cropped face, cropped chin, cropped forehead, "
            "extreme zoom on one eye, cut off face"
        )
    if key == "turnaround_front":
        return (
            "back view, from behind, rear view, facing away, "
            "side profile, profile view, looking away, "
            "upper body only, portrait, close-up, cropped feet, cropped legs, bust shot"
        )
    if key == "turnaround_side":
        return (
            "front view, facing viewer, looking at viewer, face to camera, "
            "eye contact, portrait, symmetrical face, both eyes visible, "
            "chest toward camera, three-quarter view, back view, from behind, "
            "rear view, symmetrical front portrait, "
            "upper body only, close-up, cropped feet, cropped legs"
        )
    if key == "turnaround_back":
        return (
            "face, facial features, eyes, nose, mouth, looking at viewer, "
            "front view, facing camera, portrait, side profile, three-quarter view, "
            "eye contact, smile facing camera, "
            "upper body only, close-up, cropped feet, cropped legs"
        )
    return ""


# Avoid the phrase "turnaround sheet" — it pulls multi-figure reference plates.
_TURNAROUND_BASE = (
    "solo, 1person, only one character, single figure, "
    "FULL BODY visible head to toe, feet visible on ground, entire figure in frame, "
    "standing upright, arms relaxed at sides, "
    "centered composition, plain seamless white background, studio lighting, "
    "guofeng anime style, consistent character design, "
    "single camera angle, orthographic character reference photo, "
    "no crop, no close-up, no upper body only"
)

TURNAROUND_SLOTS: list[tuple[str, str, str]] = [
    (
        "turnaround_front",
        "三视图正面",
        "FULL BODY front view, head to toe, feet visible, entire character in frame, "
        "facing viewer, looking at viewer, face fully visible, chest toward camera, "
        "standing A-pose or neutral, "
        f"{_TURNAROUND_BASE}",
    ),
    (
        "turnaround_side",
        "三视图侧面",
        "from side, profile, side view, from the side, 90 degree side profile, "
        "STRICT side view only, STRICT 90-degree side profile, "
        "FULL BODY head to toe, feet visible, "
        "head in profile silhouette, one ear visible, nose pointing sideways, "
        "ONLY one eye visible or eye not visible, looking away, "
        "body parallel to camera plane, chest not toward camera, no front face, "
        "no three-quarter view, no facing viewer, no looking at viewer, "
        "orthographic side character turnaround, "
        f"{_TURNAROUND_BASE}",
    ),
    (
        "turnaround_back",
        "三视图背面",
        "from behind, back, rear view, back view, facing away, "
        "STRICT rear view only, STRICT back view from behind, "
        "FULL BODY head to toe, feet visible, "
        "back of head only, no face, no eyes, no nose, no mouth, "
        "spine toward camera, back of outfit fully visible, "
        "no front view, no looking at viewer, no face visible, "
        "orthographic rear character turnaround, "
        f"{_TURNAROUND_BASE}",
    ),
]

# Face-only headshots for LoRA expression coverage (not half/full body).
# Lead with strong, mutually exclusive mouth/eye/brow cues so slots don't collapse.
_EXPRESSION_BASE = (
    "solo, 1person, complete face fully visible, forehead to chin in frame, "
    "both eyes nose and mouth visible, head centered with slight headroom, "
    "facial close-up headshot, hair and face only, shoulders barely visible ok, "
    "no body, no torso, no hands, no arms, no legs, no feet, "
    "no extreme crop, no half face, no cropped chin, no cropped forehead, "
    "looking at viewer, plain seamless white background, studio lighting, "
    "guofeng anime style, consistent character face, "
    "exaggerated readable expression, clear emotion, distinct from other expressions"
)

EXPRESSION_SLOTS: list[tuple[str, str, str]] = [
    (
        "expr_calm",
        "平静",
        "(calm neutral expression:1.25), relaxed brows, soft eyes, closed mouth, "
        "no smile no frown, serene composed face, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_smile",
        "微笑",
        "(gentle closed-mouth smile:1.3), lips upturned at corners, soft warm eyes, "
        "slight cheek raise, friendly smile expression, not laughing, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_happy",
        "开心",
        "(happy joyful expression:1.35), (big open-mouth grin laugh:1.3), teeth visible, "
        "eyes narrowed happily, raised cheeks, cheerful laughing face, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_confused",
        "疑惑",
        "(confused puzzled expression:1.35), (one eyebrow raised:1.25), furrowed other brow, "
        "head tilt, questioning eyes, slightly open mouth, unsure look, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_angry",
        "愤怒",
        "(angry furious expression:1.45), (deep frown:1.35), (furrowed brows:1.3), "
        "(glare stare:1.3), teeth clenched or snarl, intense eyes, scowling face, "
        "no smile, 愤怒咬牙瞪眼皱眉, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_sad",
        "悲伤",
        "(sad sorrowful expression:1.4), (teary wet eyes:1.3), (downturned mouth:1.3), "
        "inner brows raised, trembling lips, crying face, no smile, 悲伤落泪, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_surprised",
        "惊讶",
        "(surprised shocked expression:1.45), (wide eyes:1.35), (raised eyebrows:1.3), "
        "(open mouth O-shape:1.35), gasps, startled face, 惊讶张嘴瞪大眼睛, "
        f"{_EXPRESSION_BASE}",
    ),
    (
        "expr_shy",
        "害羞",
        "(shy embarrassed expression:1.3), blushing cheeks, averts gaze slightly, "
        "bashful small smile, nervous eyes, timid face, "
        f"{_EXPRESSION_BASE}",
    ),
]

# Extra negatives per expression so slots don't drift toward a calm/smile default.
EXPRESSION_SLOT_NEGATIVES: dict[str, str] = {
    "expr_calm": (
        "smile, grin, laugh, frown, angry, crying, open mouth, teeth, "
        "pursed smile, gentle smile"
    ),
    "expr_smile": "frown, angry, crying, open mouth laugh, teeth, scowl, shocked",
    "expr_happy": "frown, angry, sad, crying, neutral, closed mouth, scowl, solemn",
    "expr_confused": "smile, grin, laugh, angry, crying, serene, calm face",
    "expr_angry": (
        "smile, grin, laugh, gentle, serene, soft eyes, blush, "
        "pursed lips smile, closed mouth smile, calm neutral face, soft expression"
    ),
    "expr_sad": "smile, grin, laugh, angry, happy, cheerful, calm serene",
    "expr_surprised": (
        "smile, frown, closed mouth, sleepy, serene, calm face, "
        "pursed lips, thin straight mouth"
    ),
    "expr_shy": "angry, furious, scowl, wide open mouth, laughing hard",
}


def build_character_prompt(
    trigger: str,
    look: str,
    framing: str,
    *,
    gender_presentation: str | None = None,
    profile: dict | None = None,
    slot_key: str | None = None,
) -> str:
    """Gender + framing locks first; then trigger, look, appearance."""
    hints = look
    age_look = ""
    name = ""
    key = (slot_key or "").strip().lower()
    is_expr = key.startswith("expr_")
    if profile:
        name = str(profile.get("name") or "")
        look = sanitized_look_text(profile, look, for_expression=is_expr)
        hints = f"{look} {name} {profile.get('prompt_zh') or ''}"
        age_look = str(profile.get("age_look") or "").strip()
    gender = normalize_gender(
        gender_presentation or (profile or {}).get("gender_presentation"),
        text_hints=hints,
    )
    framing_s = framing.strip()
    view_mode = None
    if key == "turnaround_side" or any(
        k in framing_s.lower() for k in ("side view", "profile view", "from side")
    ):
        view_mode = "side"
    elif key == "turnaround_back" or any(
        k in framing_s.lower() for k in ("back view", "rear view", "from behind")
    ):
        view_mode = "back"
    # Side/back/expression: put camera or emotion tokens FIRST.
    view_first = view_mode in {"side", "back"} or is_expr
    # Side/back: skip face-heavy age boost English that fights profile/rear camera.
    age_boost = (
        []
        if view_mode in {"side", "back"}
        else age_appearance_english_boost(
            age_look=age_look,
            appearance=profile.get("appearance")
            if profile and isinstance(profile.get("appearance"), dict)
            else {},
            text_hints=hints,
            name=name,
        )
    )
    identity = [
        gender_lock_positive(
            gender, age_look=age_look, text_hints=hints, name=name, view_mode=view_mode
        ),
        *(concealment_lock_positive(profile) if profile else []),
        *age_boost,
        *(wardrobe_lock_tokens(profile) if profile else clothing_coverage_tokens()),
    ]
    parts: list[str] = []
    if view_first:
        parts.append(framing_s)
        parts.extend(identity)
    else:
        parts.extend(identity)
        parts.append(framing_s)
    parts.extend([trigger.strip(), look.strip()])
    if profile:
        # Resting smile only on calm sheet; other emotions must stay free.
        include_default = (not is_expr) or key == "expr_calm"
        parts.extend(
            appearance_lock_tokens(
                profile,
                for_expression=is_expr and key != "expr_calm",
                include_default_expression=include_default,
            )
        )
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = str(p).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return ", ".join(out)
