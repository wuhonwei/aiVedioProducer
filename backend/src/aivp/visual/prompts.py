from __future__ import annotations

# Shared framing / negatives for character-focused gens (avoid empty scenery).

PROBE_FRAMING = (
    "solo, 1person, looking at viewer, upper body portrait, "
    "simple background, 人物半身特写"
)

CHARACTER_NEGATIVE = (
    "lowres, blurry, inconsistent face, bad anatomy, watermark, "
    "scenery, landscape, palace, architecture, empty, no humans, "
    "out of frame, cropped head, modern clothes"
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


def gender_lock_negative(gender_presentation: str | None) -> str:
    """Extra negatives to reduce cross-gender drift on Guofeng priors."""
    g = (gender_presentation or "").strip().lower()
    if g in {"masculine", "male", "man", "男", "男性"}:
        return "1girl, woman, female, girl, feminine face, breasts"
    if g in {"feminine", "female", "woman", "女", "女性"}:
        return "1boy, man, male, boy, masculine face, beard"
    return ""


def character_negative_for(gender_presentation: str | None = None) -> str:
    extra = gender_lock_negative(gender_presentation)
    if not extra:
        return CHARACTER_NEGATIVE
    return f"{CHARACTER_NEGATIVE}, {extra}"


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
) -> str:
    parts = [CHARACTER_NEGATIVE, TURNAROUND_MULTI_NEGATIVE]
    gender = gender_lock_negative(gender_presentation)
    if gender:
        parts.append(gender)
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


def build_character_prompt(trigger: str, look: str, framing: str) -> str:
    """Framing first so solo/view locks beat scenery priors; then trigger + look."""
    parts = [p for p in (framing.strip(), trigger.strip(), look.strip()) if p]
    return ", ".join(parts)
