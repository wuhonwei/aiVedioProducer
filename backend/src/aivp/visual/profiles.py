from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths

DEFAULT_LORA_WEIGHT = 0.75

# Phrases that describe resting emotion — belong in default_expression, not bone structure.
_EXPRESSION_IN_LOOK = (
    "抿唇带笑",
    "抿唇浅笑",
    "面带微笑",
    "带笑",
    "微笑",
    "浅笑",
    "笑意",
    "慈祥笑",
)


def default_expression_of(profile: dict) -> str:
    return str(profile.get("default_expression") or "").strip()


def _strip_expression_phrases(text: str) -> str:
    out = text
    for phrase in _EXPRESSION_IN_LOOK:
        out = out.replace(phrase, "")
    # Soft temperament adjectives that fight strong emotion sheets.
    for phrase in ("温和", "柔和"):
        out = out.replace(phrase, "")
    return re.sub(r"[，,\s]+", "，", out).strip("，, ").strip()


def normalize_look_fields(profile: dict) -> dict[str, Any]:
    """Split resting expression out of structural appearance / prompt_zh.

    Identity fields (face shape, hair, outfit) must not bake in a fixed smile —
    that locks every expression sheet to the same calm/smiling mouth.
    """
    appearance = dict(profile.get("appearance") or {}) if isinstance(profile.get("appearance"), dict) else {}
    default_expr = default_expression_of(profile)

    mouth = str(appearance.get("mouth") or "").strip()
    if mouth and any(p in mouth for p in _EXPRESSION_IN_LOOK):
        if not default_expr:
            default_expr = mouth
        appearance["mouth"] = "自然唇形"

    eyes = str(appearance.get("eyes") or "").strip()
    if eyes:
        cleaned_eyes = _strip_expression_phrases(eyes)
        appearance["eyes"] = cleaned_eyes or "细眼"

    face = str(appearance.get("face") or "").strip()
    if face:
        cleaned_face = _strip_expression_phrases(face)
        # Re-compose structural face without baked smile.
        shape = str(appearance.get("face_shape") or "").strip()
        nose = str(appearance.get("nose") or "").strip()
        brows = str(appearance.get("eyebrows") or "").strip()
        mouth_s = str(appearance.get("mouth") or "").strip()
        eyes_s = str(appearance.get("eyes") or "").strip()
        parts = [p for p in (shape or None, eyes_s or None, nose or None, brows or None, mouth_s or None) if p]
        appearance["face"] = "，".join(parts) if parts else cleaned_face

    prompt_zh = str(profile.get("prompt_zh") or "").strip()
    if prompt_zh and any(p in prompt_zh for p in _EXPRESSION_IN_LOOK):
        # Pull first matching smile phrase into default_expression if missing.
        if not default_expr:
            for phrase in _EXPRESSION_IN_LOOK:
                if phrase in prompt_zh:
                    default_expr = phrase
                    break
        prompt_zh = _strip_expression_phrases(prompt_zh)

    if default_expr:
        profile["default_expression"] = default_expr
    if appearance:
        profile["appearance"] = appearance
    if prompt_zh:
        profile["prompt_zh"] = prompt_zh
    return profile


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically so concurrent readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_profile_json(path: Path) -> dict[str, Any] | None:
    """Load profile JSON; return None if missing/empty/corrupt (race-safe)."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def slug_trigger(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    ascii_part = re.sub(r"[^a-z0-9]+", "", text)
    if ascii_part and re.search(r"[a-z]", ascii_part):
        base = ascii_part[:24]
    else:
        base = "c" + "".join(f"{ord(ch):x}" for ch in (name or "x")[:8])
    return f"{base}_aivp"


def load_major_characters(bible: dict) -> list[dict[str, Any]]:
    chars = bible.get("characters") or []
    majors = [c for c in chars if c.get("tier") == "major"]
    if majors:
        return majors
    return list(chars)[:8]


def _anchors_from_profile(profile: dict) -> tuple[str, str]:
    trigger = str(profile.get("trigger") or "")
    look = (profile.get("prompt_zh") or "").strip()
    appearance = profile.get("appearance") if isinstance(profile.get("appearance"), dict) else {}
    wardrobe = profile.get("wardrobe") if isinstance(profile.get("wardrobe"), dict) else {}
    bits = [trigger]
    for key in ("hair", "face", "eyes", "body"):
        val = appearance.get(key)
        if val:
            bits.append(str(val))
    if wardrobe.get("default"):
        bits.append(str(wardrobe["default"]))
    if look and look not in " ".join(bits):
        bits.append(look)
    positive = ", ".join(b for b in bits if b)
    gender = str(profile.get("gender_presentation") or "")
    neg_bits = ["wrong gender", "different hairstyle", "different outfit", "modern clothes"]
    if gender == "male":
        neg_bits.append("female")
    elif gender == "female":
        neg_bits.append("male")
    return positive, ", ".join(neg_bits)


def ensure_profile(vpaths: VisualPaths, character: dict) -> dict[str, Any]:
    cid = str(character.get("id") or "unknown")
    vpaths.ensure_character(cid)
    path = vpaths.profile_json(cid)
    profile = read_profile_json(path)
    if profile is None:
        name = str(character.get("name") or cid)
        profile = {
            "character_id": cid,
            "name": name,
            "trigger": slug_trigger(name),
            "status": "profiled",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "lora_file": None,
        }
    # Refresh prompt anchors from bible character card.
    profile["character_id"] = cid
    profile["name"] = character.get("name") or profile.get("name")
    profile["prompt_zh"] = character.get("prompt_zh") or profile.get("prompt_zh") or ""
    profile["gender_presentation"] = (
        character.get("gender_presentation")
        or profile.get("gender_presentation")
        or "unspecified"
    )
    profile["age_look"] = character.get("age_look") or profile.get("age_look") or ""
    profile["appearance"] = character.get("appearance") or profile.get("appearance") or {}
    profile["wardrobe"] = character.get("wardrobe") or profile.get("wardrobe") or {}
    profile["consistency_anchors"] = (
        character.get("consistency_anchors") or profile.get("consistency_anchors") or []
    )
    if character.get("default_expression"):
        profile["default_expression"] = character.get("default_expression")
    profile = normalize_look_fields(profile)
    if not profile.get("trigger"):
        profile["trigger"] = slug_trigger(str(profile.get("name") or cid))

    # LoRA lifecycle defaults (do not overwrite existing progress).
    profile.setdefault("train_status", "not_started")
    profile.setdefault("probe_status", "not_started")
    if "lora_ready" not in profile:
        # Migrate legacy status=lora_ready → explicit flag.
        profile["lora_ready"] = profile.get("status") == "lora_ready"
    profile.setdefault("lora_weight_default", DEFAULT_LORA_WEIGHT)
    pos, neg = _anchors_from_profile(profile)
    # Always refresh anchors after look-field normalize so smile phrases leave positive_anchor.
    profile["positive_anchor"] = pos
    profile["negative_anchor"] = neg

    atomic_write_json(path, profile)
    return profile


def save_profile(vpaths: VisualPaths, profile: dict) -> dict:
    cid = str(profile.get("character_id") or "unknown")
    path = vpaths.profile_json(cid)
    atomic_write_json(path, profile)
    return profile


def character_status(vpaths: VisualPaths, character_id: str, profile: dict) -> dict[str, Any]:
    cand = list(vpaths.candidates_dir(character_id).glob("*.png"))
    curated = list(vpaths.curated_dir(character_id).glob("*.png"))
    sheets = list(vpaths.sheets_dir(character_id).glob("*.png"))
    gens = list(vpaths.generations_dir(character_id).glob("*.png"))
    loras = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    lora_ready = bool(profile.get("lora_ready"))
    look_lock = profile.get("look_lock") if isinstance(profile.get("look_lock"), dict) else None
    look_lock_ready = bool(
        look_lock and (vpaths.character_dir(character_id) / "look_lock" / "ref.png").exists()
    )
    archive_dir = vpaths.character_dir(character_id) / "look_lock_archive"
    archive = list(archive_dir.glob("*.png")) if archive_dir.exists() else []
    return {
        **profile,
        "candidate_count": len(cand),
        "curated_count": len(curated),
        "sheet_count": len(sheets),
        "generation_count": len(gens),
        "train_status": profile.get("train_status") or "not_started",
        "probe_status": profile.get("probe_status") or "not_started",
        "bootstrap_status": profile.get("bootstrap_status") or "not_started",
        "bootstrap_warnings": profile.get("bootstrap_warnings") or [],
        "lora_ready": lora_ready,
        "look_lock": look_lock,
        "look_lock_ready": look_lock_ready,
        "look_lock_archive": sorted((p.name for p in archive), reverse=True),
        "lora_files": [p.name for p in loras],
        # Newest first so batch-generated thumbs appear at the top without hunting.
        "candidates": sorted((p.name for p in cand), reverse=True),
        "curated": sorted((p.name for p in curated), reverse=True),
        "sheets": sorted((p.name for p in sheets), reverse=True),
        "generations": sorted((p.name for p in gens), reverse=True),
    }


def build_lora_refs(
    vpaths: VisualPaths,
    character_ids: list[str],
    *,
    only_ready: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keyframe-ready LoRA refs for cast characters. Returns (refs, warnings)."""
    refs: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cid in character_ids:
        path = vpaths.profile_json(cid)
        if not path.exists():
            warnings.append(f"profile_missing:{cid}")
            continue
        profile = json.loads(path.read_text(encoding="utf-8"))
        ready = bool(profile.get("lora_ready"))
        if only_ready and not ready:
            warnings.append(f"lora_not_ready:{cid}")
            continue
        lora_file = profile.get("lora_file")
        if not lora_file:
            local = list(vpaths.lora_dir(cid).glob("*.safetensors"))
            lora_file = local[0].name if local else None
        if not lora_file:
            warnings.append(f"lora_file_missing:{cid}")
            continue
        refs.append(
            {
                "character_id": cid,
                "file": str(lora_file),
                "trigger": profile.get("trigger") or "",
                "weight": float(profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT),
                "positive_anchor": profile.get("positive_anchor") or "",
                "negative_anchor": profile.get("negative_anchor") or "",
            }
        )
    return refs, warnings
