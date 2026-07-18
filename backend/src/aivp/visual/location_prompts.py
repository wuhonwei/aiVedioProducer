"""Prompts for empty-scene location plates."""
from __future__ import annotations

from typing import Any

ESTABLISHING_VIEWS = (
    "wide establishing shot, empty scenery, no people, architecture and environment only",
    "wide environmental shot, empty place, depth of field, no characters",
    "three quarter establishing view, empty plaza or path, no humans",
    "slightly elevated wide shot, empty location, atmospheric depth, no people",
    "distant establishing landscape with place structures, unpopulated",
)

EXPAND_VIEWS = (
    "wide establishing shot, empty scenery, no people",
    "three quarter environmental angle, empty place, no humans",
    "side angle empty architecture, no characters",
    "reverse establishing empty view, no people",
    "dawn light empty scenery, misty atmosphere, no people",
    "dusk golden hour empty place, no humans",
    "light fog empty environment, no characters",
    "material close-up of stone wood water mist belonging to this place, no people",
)

_BASE_NEG = (
    "person, people, human, man, woman, child, face, portrait, character sheet, "
    "crowd, silhouette figure, anime girl, anime boy, close-up face, "
    "text, watermark, blurry, low quality"
)


def location_negative_for(profile: dict | None = None, *, tuning: dict | None = None) -> str:
    neg = _BASE_NEG
    tun = tuning or {}
    if tun.get("extra_negative"):
        neg = f"{neg}, {tun['extra_negative']}"
    return neg


def build_location_candidate_prompt(profile: dict, view: str) -> str:
    trigger = str(profile.get("trigger") or "").strip()
    look = str(profile.get("prompt_zh") or "").strip()
    name = str(profile.get("name") or "").strip()
    materials = profile.get("materials") if isinstance(profile.get("materials"), list) else []
    palette = profile.get("palette") if isinstance(profile.get("palette"), list) else []
    era = str(profile.get("era_mood") or "").strip()
    bits = [
        trigger,
        name,
        look,
        era,
        "，".join(str(m) for m in materials[:4] if m),
        "，".join(str(p) for p in palette[:4] if p),
        "guofeng anime empty location plate",
        "no people, empty scene, environment only",
        view,
    ]
    return ", ".join(b for b in bits if b)


def apply_location_tuning_to_prompt(prompt: str, tuning: dict | None) -> str:
    tun = tuning or {}
    extras: list[str] = []
    if tun.get("full_empty_boost"):
        extras.append("completely empty of people, no figures anywhere")
    if tun.get("wide_establishing_boost"):
        extras.append("ultra wide establishing shot, full environment readable")
    if tun.get("place_token_boost"):
        extras.append("clear landmark architecture and materials matching the location card")
    if extras:
        return f"{prompt}, {', '.join(extras)}"
    return prompt
