from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from aivp.visual.paths import VisualPaths

DEFAULT_LORA_WEIGHT = 0.75


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
    if path.exists():
        profile = json.loads(path.read_text(encoding="utf-8"))
    else:
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
    profile.setdefault("positive_anchor", pos)
    profile.setdefault("negative_anchor", neg)

    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def save_profile(vpaths: VisualPaths, profile: dict) -> dict:
    cid = str(profile.get("character_id") or "unknown")
    path = vpaths.profile_json(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def character_status(vpaths: VisualPaths, character_id: str, profile: dict) -> dict[str, Any]:
    cand = list(vpaths.candidates_dir(character_id).glob("*.png"))
    curated = list(vpaths.curated_dir(character_id).glob("*.png"))
    sheets = list(vpaths.sheets_dir(character_id).glob("*.png"))
    gens = list(vpaths.generations_dir(character_id).glob("*.png"))
    loras = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    lora_ready = bool(profile.get("lora_ready"))
    return {
        **profile,
        "candidate_count": len(cand),
        "curated_count": len(curated),
        "sheet_count": len(sheets),
        "generation_count": len(gens),
        "train_status": profile.get("train_status") or "not_started",
        "probe_status": profile.get("probe_status") or "not_started",
        "lora_ready": lora_ready,
        "lora_files": [p.name for p in loras],
        "candidates": sorted(p.name for p in cand),
        "curated": sorted(p.name for p in curated),
        "sheets": sorted(p.name for p in sheets),
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
