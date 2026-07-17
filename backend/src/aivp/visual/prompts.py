from __future__ import annotations

# Shared framing / negatives for character-focused gens (avoid empty scenery).

PROBE_FRAMING = (
    "solo, 1person, looking at viewer, upper body portrait, "
    "simple background, 人物半身特写"
)

CHARACTER_NEGATIVE = (
    "lowres, blurry, inconsistent face, bad anatomy, watermark, "
    "scenery, landscape, palace, architecture, empty, no humans, "
    "out of frame, cropped head, modern clothes, western clothes, "
    "school uniform, armor, wedding dress, costume change, different outfit, "
    "multiple people, 2people, 2girls, 2boys, crowd"
)

# "turnaround sheet / character sheet" in anime priors often means multi-view plate.
TURNAROUND_MULTI_NEGATIVE = (
    "multiple people, 2people, 2girls, 2boys, 3girls, 3boys, crowd, twins, clone, "
    "character sheet, turnaround sheet, model sheet, reference sheet, "
    "multiple views, collage, split screen, grid layout, triptych, "
    "front and back together, three views in one image, mirror, reflection, "
    "extra person, duplicate character, group shot"
)

SHEET_NEGATIVE = CHARACTER_NEGATIVE + ", " + TURNAROUND_MULTI_NEGATIVE

_OUTFIT_DRIFT_NEGATIVE = (
    "costume change, different outfit, outfit swap, clothing mismatch, "
    "random clothes, bare shoulders, revealing clothes, modern streetwear, "
    "hoodie, t-shirt, jeans, suit, dress suit"
)


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


def gender_lock_positive(gender: str) -> str:
    if gender == "male":
        return "1boy, solo, male, masculine face, young man"
    if gender == "female":
        return "1girl, solo, female, feminine face, young woman"
    return "solo, 1person"


def gender_lock_negative(gender_presentation: str | None) -> str:
    """Extra negatives to reduce cross-gender drift on Guofeng priors."""
    g = normalize_gender(gender_presentation)
    if g == "male":
        return (
            "1girl, woman, female, girl, feminine face, breasts, "
            "lipstick, long eyelashes, makeup"
        )
    if g == "female":
        return "1boy, man, male, boy, masculine face, beard, adam's apple"
    return ""


def character_negative_for(gender_presentation: str | None = None) -> str:
    parts = [CHARACTER_NEGATIVE, _OUTFIT_DRIFT_NEGATIVE]
    extra = gender_lock_negative(gender_presentation)
    if extra:
        parts.append(extra)
    return ", ".join(parts)


def candidate_negative_for(profile: dict) -> str:
    gender = normalize_gender(
        profile.get("gender_presentation"),
        text_hints=f"{profile.get('prompt_zh') or ''} {profile.get('name') or ''}",
    )
    return character_negative_for(gender)


def appearance_lock_tokens(profile: dict) -> list[str]:
    """Stable look tokens from profile appearance / wardrobe / anchors."""
    tokens: list[str] = []
    appearance = profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {}
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
        val = appearance.get(key)
        if val:
            tokens.append(str(val).strip())
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    default_outfit = str(wardrobe.get("default") or "").strip()
    if default_outfit:
        tokens.append(f"wearing {default_outfit}")
        tokens.append(f"身着{default_outfit}")
        tokens.append("same outfit, identical clothing")
    anchors = profile.get("consistency_anchors") or []
    if isinstance(anchors, list):
        for a in anchors:
            t = str(a).strip()
            if t and t not in tokens:
                tokens.append(t)
    age = str(profile.get("age_look") or "").strip()
    if age:
        tokens.append(age)
    return [t for t in tokens if t]


def build_candidate_prompt(profile: dict, view: str) -> str:
    """Gender + look + wardrobe locked early; view/framing last."""
    trigger = str(profile.get("trigger") or "character_aivp").strip()
    look = str(profile.get("prompt_zh") or profile.get("name") or trigger).strip()
    gender = normalize_gender(
        profile.get("gender_presentation"),
        text_hints=f"{look} {profile.get('name') or ''}",
    )
    parts = [
        gender_lock_positive(gender),
        trigger,
        look,
        *appearance_lock_tokens(profile),
        view,
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


def _view_lock_negative(slot_key: str | None) -> str:
    key = (slot_key or "").strip().lower()
    if key == "turnaround_front":
        return (
            "back view, from behind, rear view, facing away, "
            "side profile, profile view, looking away"
        )
    if key == "turnaround_side":
        return (
            "front view, facing viewer, looking at viewer, "
            "back view, from behind, rear view, three-quarter view"
        )
    if key == "turnaround_back":
        return (
            "face, facial features, looking at viewer, front view, "
            "eyes visible, smile, portrait, facing camera"
        )
    return ""


def sheet_negative_for(
    gender_presentation: str | None = None,
    *,
    slot_key: str | None = None,
    text_hints: str = "",
) -> str:
    gender = normalize_gender(gender_presentation, text_hints=text_hints)
    parts = [CHARACTER_NEGATIVE, TURNAROUND_MULTI_NEGATIVE, _OUTFIT_DRIFT_NEGATIVE]
    gneg = gender_lock_negative(gender)
    if gneg:
        parts.append(gneg)
    view = _view_lock_negative(slot_key)
    if view:
        parts.append(view)
    return ", ".join(parts)


# Avoid the phrase "turnaround sheet" — it pulls multi-figure reference plates.
_TURNAROUND_BASE = (
    "solo, 1person, only one character, single figure, "
    "full body visible head to toe, standing upright, arms relaxed at sides, "
    "centered composition, plain seamless white background, studio lighting, "
    "guofeng anime style, consistent character design, "
    "single camera angle, orthographic character reference photo"
)

TURNAROUND_SLOTS: list[tuple[str, str, str]] = [
    (
        "turnaround_front",
        "三视图正面",
        f"{_TURNAROUND_BASE}, front view, facing viewer, looking at viewer, "
        "face fully visible, chest toward camera",
    ),
    (
        "turnaround_side",
        "三视图侧面",
        f"{_TURNAROUND_BASE}, strict side profile view, from the side, "
        "head in profile, one ear visible, body parallel to camera",
    ),
    (
        "turnaround_back",
        "三视图背面",
        f"{_TURNAROUND_BASE}, rear view, from behind, back of head, "
        "facing away from viewer, no face visible, back of outfit visible",
    ),
]

EXPRESSION_SLOTS: list[tuple[str, str, str]] = [
    (
        "expr_calm",
        "平静",
        "solo, 1person, facial close-up, calm neutral expression, looking at viewer, simple background",
    ),
    (
        "expr_smile",
        "微笑",
        "solo, 1person, facial close-up, gentle smile, looking at viewer, simple background",
    ),
    (
        "expr_happy",
        "开心",
        "solo, 1person, facial close-up, happy joyful expression, looking at viewer, simple background",
    ),
    (
        "expr_confused",
        "疑惑",
        "solo, 1person, facial close-up, confused puzzled expression, looking at viewer, simple background",
    ),
    (
        "expr_angry",
        "愤怒",
        "solo, 1person, facial close-up, angry expression, looking at viewer, simple background",
    ),
    (
        "expr_sad",
        "悲伤",
        "solo, 1person, facial close-up, sad expression, looking at viewer, simple background",
    ),
    (
        "expr_surprised",
        "惊讶",
        "solo, 1person, facial close-up, surprised expression, looking at viewer, simple background",
    ),
    (
        "expr_shy",
        "害羞",
        "solo, 1person, facial close-up, shy embarrassed expression, looking at viewer, simple background",
    ),
]


def build_character_prompt(
    trigger: str,
    look: str,
    framing: str,
    *,
    gender_presentation: str | None = None,
    profile: dict | None = None,
) -> str:
    """Gender + framing locks first; then trigger, look, appearance."""
    hints = look
    if profile:
        hints = f"{look} {profile.get('name') or ''}"
    gender = normalize_gender(
        gender_presentation or (profile or {}).get("gender_presentation"),
        text_hints=hints,
    )
    parts = [
        gender_lock_positive(gender),
        framing.strip(),
        trigger.strip(),
        look.strip(),
    ]
    if profile:
        parts.extend(appearance_lock_tokens(profile))
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = str(p).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return ", ".join(out)
