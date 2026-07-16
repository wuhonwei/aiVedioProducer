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

SHEET_NEGATIVE = CHARACTER_NEGATIVE + ", multiple people, crowd"

TURNAROUND_SLOTS: list[tuple[str, str, str]] = [
    (
        "turnaround_front",
        "三视图正面",
        "character turnaround sheet, front view, full body, standing, "
        "plain white background, guofeng anime, consistent character design",
    ),
    (
        "turnaround_side",
        "三视图侧面",
        "character turnaround sheet, side profile view, full body, standing, "
        "plain white background, guofeng anime, consistent character design",
    ),
    (
        "turnaround_back",
        "三视图背面",
        "character turnaround sheet, back view, full body, standing, "
        "plain white background, guofeng anime, consistent character design",
    ),
]

EXPRESSION_SLOTS: list[tuple[str, str, str]] = [
    ("expr_calm", "平静", "facial close-up, calm neutral expression, looking at viewer"),
    ("expr_smile", "微笑", "facial close-up, gentle smile, looking at viewer"),
    ("expr_happy", "开心", "facial close-up, happy joyful expression, looking at viewer"),
    ("expr_confused", "疑惑", "facial close-up, confused puzzled expression, looking at viewer"),
    ("expr_angry", "愤怒", "facial close-up, angry expression, looking at viewer"),
    ("expr_sad", "悲伤", "facial close-up, sad expression, looking at viewer"),
    ("expr_surprised", "惊讶", "facial close-up, surprised expression, looking at viewer"),
    ("expr_shy", "害羞", "facial close-up, shy embarrassed expression, looking at viewer"),
]


def build_character_prompt(trigger: str, look: str, framing: str) -> str:
    parts = [p for p in (trigger.strip(), look.strip(), framing.strip()) if p]
    return "，".join(parts)
