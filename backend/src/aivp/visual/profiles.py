from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from aivp.visual.paths import VisualPaths


def slug_trigger(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    # Keep ascii alnum; Chinese names become pinyin-less stable slug via hex fallback.
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
    # Fallback: top characters if tier missing (older bibles).
    return list(chars)[:8]


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
    profile["appearance"] = character.get("appearance") or profile.get("appearance") or {}
    profile["wardrobe"] = character.get("wardrobe") or profile.get("wardrobe") or {}
    profile["consistency_anchors"] = (
        character.get("consistency_anchors") or profile.get("consistency_anchors") or []
    )
    if not profile.get("trigger"):
        profile["trigger"] = slug_trigger(str(profile.get("name") or cid))
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def character_status(vpaths: VisualPaths, character_id: str, profile: dict) -> dict[str, Any]:
    cand = list(vpaths.candidates_dir(character_id).glob("*.png"))
    curated = list(vpaths.curated_dir(character_id).glob("*.png"))
    loras = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    return {
        **profile,
        "candidate_count": len(cand),
        "curated_count": len(curated),
        "lora_ready": bool(loras) or bool(profile.get("lora_file")),
        "lora_files": [p.name for p in loras],
        "candidates": sorted(p.name for p in cand),
        "curated": sorted(p.name for p in curated),
    }
