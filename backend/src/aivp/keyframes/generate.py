from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.keyframes.paths import KeyframePaths
from aivp.keyframes.store import next_candidate_stem
from aivp.paths import ProjectPaths
from aivp.visual.image_backend import ComfyImageBackend, ImageBackend, StubImageBackend
from aivp.visual.location_profiles import read_location_profile
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import read_profile_json
from aivp.visual.t2i import generate_shot_with_loras

_MAX_LORAS = 3
_DEFAULT_NEGATIVE = "lowres, blurry, bad anatomy, watermark, text"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_shot(project_paths: ProjectPaths, shot_id: str) -> dict[str, Any]:
    script_path = project_paths.shot_script_json
    if not script_path.exists():
        raise FileNotFoundError("shot_script_missing")
    doc = json.loads(script_path.read_text(encoding="utf-8"))
    for shot in doc.get("shots") or []:
        if shot.get("shot_id") == shot_id:
            return shot
    raise KeyError(f"shot_not_found:{shot_id}")


def _character_lora_ready(vpaths: VisualPaths, character_id: str) -> bool:
    profile = read_profile_json(vpaths.profile_json(character_id))
    if not profile or not profile.get("lora_ready"):
        return False
    lora_file = profile.get("lora_file")
    if isinstance(lora_file, str) and lora_file.strip():
        return True
    return bool(list(vpaths.lora_dir(character_id).glob("*.safetensors")))


def _location_lora_ready(vpaths: VisualPaths, location_id: str) -> bool:
    profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
    if not profile.get("lora_ready"):
        return False
    lora_file = profile.get("lora_file")
    if isinstance(lora_file, str) and lora_file.strip():
        return True
    return bool(list(vpaths.location_lora_dir(location_id).glob("*.safetensors")))


def _clear_shot_candidates(kpaths: KeyframePaths, shot_id: str) -> None:
    cand_dir = kpaths.candidates_dir(shot_id)
    if cand_dir.exists():
        for path in cand_dir.iterdir():
            if path.suffix.lower() in {".png", ".json"}:
                path.unlink()
    selected = kpaths.selected_json(shot_id)
    if selected.exists():
        selected.unlink()


def _backend_name(backend: ImageBackend) -> str:
    if isinstance(backend, StubImageBackend):
        return "stub"
    if isinstance(backend, ComfyImageBackend):
        return "comfy"
    return type(backend).__name__.lower()


def _build_warnings(
    vpaths: VisualPaths,
    *,
    character_ids: list[str],
    location_id: str | None,
    use_location_lora: bool,
) -> tuple[list[str], list[str], bool]:
    """Return (warnings, stacked_character_ids, location_lora_slot)."""
    warnings: list[str] = []
    for cid in character_ids:
        if not _character_lora_ready(vpaths, cid):
            warnings.append(f"character_lora_not_ready:{cid}")

    location_lora_slot = False
    if location_id:
        if not use_location_lora:
            warnings.append("location_lora_disabled_by_default")
        elif not _location_lora_ready(vpaths, location_id):
            warnings.append("location_lora_not_ready")
        else:
            location_lora_slot = True

    loc_slots = 1 if location_lora_slot else 0
    max_chars = max(0, _MAX_LORAS - loc_slots)
    stacked_character_ids = list(character_ids)
    if len(stacked_character_ids) > max_chars:
        warnings.append("too_many_loras")
        stacked_character_ids = stacked_character_ids[:max_chars]

    return warnings, stacked_character_ids, location_lora_slot


def generate_keyframes(
    project_paths: ProjectPaths,
    vpaths: VisualPaths,
    kpaths: KeyframePaths,
    backend: ImageBackend,
    shot_id: str,
    *,
    count: int = 4,
    use_location_lora: bool = False,
    force: bool = False,
    prompt_override: str = "",
    negative_override: str = "",
    settings=None,
) -> dict[str, Any]:
    shot = _load_shot(project_paths, shot_id)
    asset_refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    character_ids = list(asset_refs.get("characters") or [])
    locations = list(asset_refs.get("locations") or [])
    location_id = str(locations[0]) if locations else None

    prompt = (prompt_override or shot.get("visual_prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt_required")
    negative = (
        (negative_override or shot.get("negative_prompt") or _DEFAULT_NEGATIVE).strip()
    )

    kpaths.ensure_shot(shot_id)
    if force:
        _clear_shot_candidates(kpaths, shot_id)

    warnings, stacked_character_ids, _ = _build_warnings(
        vpaths,
        character_ids=character_ids,
        location_id=location_id,
        use_location_lora=use_location_lora,
    )

    count = min(8, max(1, int(count)))

    candidates: list[dict[str, str]] = []
    last_out: dict[str, Any] | None = None
    for _ in range(count):
        out = generate_shot_with_loras(
            vpaths,
            backend,
            prompt=prompt,
            location_id=location_id,
            character_ids=stacked_character_ids,
            negative=negative,
            shot_id=shot_id,
            use_location_lora=use_location_lora,
            settings=settings,
        )
        last_out = out

        stem = next_candidate_stem(kpaths, shot_id)
        filename = f"{stem}.png"
        dest = kpaths.candidates_dir(shot_id) / filename
        shutil.copy2(Path(out["path"]), dest)

        created_at = datetime.now(timezone.utc).isoformat()
        sidecar = {
            "file": filename,
            "shot_id": shot_id,
            "prompt": out.get("prompt") or prompt,
            "negative": negative,
            "loras": out.get("loras") or [],
            "created_at": created_at,
            "quality": {"status": "unchecked", "warnings": []},
        }
        _write_json(dest.with_suffix(".json"), sidecar)
        candidates.append({"file": filename, "url": ""})

    generation: dict[str, Any] = {
        "shot_id": shot_id,
        "prompt": prompt,
        "negative": negative,
        "character_ids": character_ids,
        "location_id": location_id,
        "use_location_lora": use_location_lora,
        "loras": (last_out or {}).get("loras") or [],
        "backend": _backend_name(backend),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "warnings": warnings,
    }
    _write_json(kpaths.generation_json(shot_id), generation)

    return {
        "shot_id": shot_id,
        "status": "succeeded",
        "candidates": candidates,
        "warnings": warnings,
        "generation": generation,
    }
