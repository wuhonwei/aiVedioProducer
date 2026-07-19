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
from aivp.pipeline.shot_upgrade import build_name_to_id_map
from aivp.visual.image_backend import ComfyImageBackend, ImageBackend, StubImageBackend
from aivp.visual.location_profiles import read_location_profile
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import read_profile_json
from aivp.visual.t2i import generate_shot_with_loras

_MAX_LORAS = 3
_DEFAULT_NEGATIVE = "lowres, blurry, bad anatomy, watermark, text"

_SHEET_ZH_MARKERS = (
    "国风动画角色定妆",
    "角色定妆",
    "定妆照",
    "三视图",
    "turnaround",
    "character sheet",
    "model sheet",
    "reference sheet",
)

_SHOT_SIZE_FRAMING: dict[str, str] = {
    "establishing": "wide shot, establishing shot, full environment visible, cinematic composition",
    "wide": "wide shot, full body visible, environment in frame, cinematic anime still",
    "full": "full body shot, head to toe in frame, cinematic anime still",
    "medium": "medium shot, half body, waist up, cinematic anime still",
    "medium_wide": "medium wide shot, full body visible, environment in frame, cinematic anime still",
    "medium_close": "medium close-up, chest up, cinematic anime still",
    "close": "close-up, face and shoulders, cinematic anime still",
    "insert": "insert shot, detail focus, cinematic anime still",
    "over_shoulder": "over-the-shoulder shot, cinematic anime still",
}

_KEYFRAME_ACTION_NEGATIVE = (
    "portrait, solo character, standing still, looking at viewer, facing camera, "
    "character lineup, group photo, static pose, neutral pose, A-pose, "
    "character reference, bust shot, headshot, "
    "formal portrait, silhouette portrait, solo 1person, peaceful background, centered composition"
)

_ACTION_ATTACK_KEYWORDS = (
    "挥刀",
    "攻击",
    "倒地",
    "冲出",
    "打斗",
    "战斗",
    "厮杀",
)

_ACTION_SCENE_LOCK = (
    "dynamic action scene, multiple people, sword attack in progress, wounded man falling, "
    "chaotic crowd, wooden pier dock riverside, guofeng anime cinematic still"
)

_KEYFRAME_SHEET_NEGATIVE = (
    "character sheet, turnaround sheet, model sheet, reference sheet, "
    "multiple views, plain white background, studio lighting, "
    "A-pose, orthographic character reference, 定妆, 三视图, 角色设定图"
)


def _strip_sheet_language(text: str) -> str:
    out = (text or "").strip()
    for marker in _SHEET_ZH_MARKERS:
        out = out.replace(marker, "")
    while "；；" in out:
        out = out.replace("；；", "；")
    return out.strip("；，, ").strip()


def _normalize_shot_size(raw: str) -> str:
    """Map 'medium wide' / 'medium-wide' to dict keys like medium_wide."""
    key = str(raw or "").strip().lower().replace("-", " ")
    key = "_".join(part for part in key.split() if part)
    aliases = {
        "mediumwide": "medium_wide",
        "mediumclose": "medium_close",
        "closeup": "close",
        "close_up": "close",
        "fullbody": "full",
        "full_body": "full",
        "establishing_shot": "establishing",
        "wide_shot": "wide",
        "overshoulder": "over_shoulder",
        "over_the_shoulder": "over_shoulder",
    }
    return aliases.get(key, key)


_ACTION_FRAMING_MARKERS = (
    "攻击",
    "战斗",
    "挥刀",
    "冲出",
    "倒地",
    "人群",
    "attack",
    "combat",
    "fight",
    "strike",
    "charge",
    "fall",
    "crowd",
)

_DOCK_MARKERS = ("码头", "渡口", "dock", "pier", "wharf")


def _scene_text_for_framing(shot: dict[str, Any]) -> str:
    visual = str(shot.get("visual_prompt") or "")
    action = str(shot.get("action") or "")
    return f"{visual} {action}"


def _is_action_scene(shot: dict[str, Any]) -> bool:
    text = _scene_text_for_framing(shot)
    if any(m in text for m in _ACTION_ATTACK_KEYWORDS):
        return True
    return any(m in text for m in _ACTION_FRAMING_MARKERS)


def _is_attack_action_scene(shot: dict[str, Any]) -> bool:
    text = _scene_text_for_framing(shot)
    return any(m in text for m in _ACTION_ATTACK_KEYWORDS)


def _has_dock_setting(shot: dict[str, Any]) -> bool:
    text = _scene_text_for_framing(shot)
    loc = str(shot.get("location") or shot.get("location_name") or "")
    return any(m in text or m in loc for m in _DOCK_MARKERS)


def _shot_framing_tokens(shot: dict[str, Any]) -> str:
    shot_type = _normalize_shot_size(str(shot.get("shot_type") or ""))
    camera = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
    size = _normalize_shot_size(
        str(camera.get("shot_size") or shot.get("shot_type") or "medium")
    )
    action_scene = _is_action_scene(shot)

    if action_scene and size in ("close", "medium_close", "medium"):
        size = "medium_wide"

    framing = (
        _SHOT_SIZE_FRAMING.get(size)
        or _SHOT_SIZE_FRAMING.get(shot_type)
        or _SHOT_SIZE_FRAMING["medium"]
    )
    if action_scene and size in ("wide", "medium_wide", "establishing", "full"):
        framing = (
            "wide dynamic action shot, full body visible, environment in frame, "
            "cinematic anime still, dynamic composition"
        )

    angle = str(camera.get("angle") or "eye level").strip()
    movement = str(camera.get("movement") or "static").strip()
    lens = str(camera.get("lens") or "").strip()
    composition = str(camera.get("composition") or "").strip()
    if action_scene and "centered" in composition.lower():
        composition = ""
    notes = str(camera.get("notes") or "").strip() if isinstance(camera.get("notes"), str) else ""
    bits = [
        framing,
        f"{angle} angle" if angle else "",
        f"{movement} camera" if movement and movement != "static" else "",
        lens,
        composition,
        notes,
        "cinematic still from anime film",
        "in-scene environment",
    ]
    if action_scene:
        bits.append("multi-character action scene, combat staging, dynamic poses")
        bits.append(
            "action in progress, mid-motion, not portrait, characters not facing camera"
        )
        if _has_dock_setting(shot):
            bits.append(
                "crowd panic, dock pier wooden planks, waterfront action on wooden dock"
            )
    return ", ".join(b for b in bits if b)


_KEYFRAME_SCENE_LOCK = (
    "characters interacting in location, narrative moment, dynamic pose, "
    "environment background visible, story beat, not portrait studio"
)


def _build_keyframe_prompt(shot: dict[str, Any], *, override: str = "") -> str:
    if override.strip():
        return _strip_sheet_language(override)

    visual = _strip_sheet_language(str(shot.get("visual_prompt") or ""))
    action = str(shot.get("action") or "").strip()
    if action and action == visual:
        action = ""

    action_scene = _is_action_scene(shot)
    attack_scene = _is_attack_action_scene(shot)
    if action_scene and action:
        scene_bits = [action]
        if visual and visual not in action:
            scene_bits.append(visual)
    else:
        scene_bits = [visual]
        if action and action not in visual:
            scene_bits.append(action)

    if attack_scene:
        scene_bits = [_ACTION_SCENE_LOCK] + scene_bits

    framing = _shot_framing_tokens(shot)
    parts = [b for b in scene_bits + [framing] if b]
    if _shot_has_characters(shot) and not attack_scene:
        parts.append(_KEYFRAME_SCENE_LOCK)
    prompt = ", ".join(parts)
    if action:
        if attack_scene:
            prompt = f"{prompt}, must depict action: {action}"
        else:
            prompt = f"画面必须表现：{action}, {prompt}, 画面必须表现：{action}"
    return prompt


def _shot_has_characters(shot: dict[str, Any]) -> bool:
    asset_refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    if asset_refs.get("characters"):
        return True
    if shot.get("cast") or shot.get("characters"):
        return True
    assets_required = (
        shot.get("assets_required") if isinstance(shot.get("assets_required"), dict) else {}
    )
    return bool(assets_required.get("characters"))


def _build_keyframe_negative(shot: dict[str, Any], override: str = "") -> str:
    base = (override or shot.get("negative_prompt") or _DEFAULT_NEGATIVE).strip()
    parts = [base, _KEYFRAME_SHEET_NEGATIVE]
    if _is_action_scene(shot):
        parts.append(_KEYFRAME_ACTION_NEGATIVE)
    if _shot_has_characters(shot):
        parts.append("empty scene, no humans, deserted")
    return ", ".join(parts)


def _resolve_name_to_id(name: str, name_to_id: dict[str, str]) -> str | None:
    key = str(name).strip()
    if not key:
        return None
    if key in name_to_id:
        return name_to_id[key]
    candidates = [
        (n, entity_id) for n, entity_id in name_to_id.items() if key.startswith(n) and len(n) >= 2
    ]
    if len(candidates) == 1:
        return candidates[0][1]
    rev = [
        (n, entity_id) for n, entity_id in name_to_id.items() if n.startswith(key) and len(key) >= 2
    ]
    if len(rev) == 1:
        return rev[0][1]
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_asset_entity_docs(project_paths: ProjectPaths) -> tuple[dict | None, dict | None]:
    entities = None
    assets = None
    if project_paths.entities_json.exists():
        entities = json.loads(project_paths.entities_json.read_text(encoding="utf-8"))
    if project_paths.assets_json.exists():
        assets = json.loads(project_paths.assets_json.read_text(encoding="utf-8"))
    return assets, entities


def _load_character_name_to_id_map(project_paths: ProjectPaths) -> dict[str, str]:
    assets, entities = _load_asset_entity_docs(project_paths)
    return build_name_to_id_map(assets, entities, kinds=("characters", "factions"))


def _load_location_name_to_id_map(project_paths: ProjectPaths) -> dict[str, str]:
    assets, entities = _load_asset_entity_docs(project_paths)
    return build_name_to_id_map(assets, entities, kinds=("locations",))


def _dedupe_preserve_order(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _resolve_shot_asset_ids(
    shot: dict[str, Any],
    character_name_to_id: dict[str, str],
    location_name_to_id: dict[str, str] | None = None,
) -> tuple[list[str], str | None]:
    """Prefer asset_refs ids; fall back to cast/location names via name maps."""
    location_map = location_name_to_id if location_name_to_id is not None else character_name_to_id
    asset_refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    character_ids = [
        str(x).strip() for x in (asset_refs.get("characters") or []) if str(x).strip()
    ]
    locations = [
        str(x).strip() for x in (asset_refs.get("locations") or []) if str(x).strip()
    ]
    location_id = locations[0] if locations else None

    assets_required = (
        shot.get("assets_required") if isinstance(shot.get("assets_required"), dict) else {}
    )

    if not character_ids:
        cast_names = list(
            assets_required.get("characters")
            or shot.get("cast")
            or shot.get("characters")
            or []
        )
        for name in cast_names:
            key = str(name).strip()
            if not key:
                continue
            character_ids.append(_resolve_name_to_id(key, character_name_to_id) or key)
    else:
        character_ids = [
            _resolve_name_to_id(key, character_name_to_id) or key for key in character_ids
        ]

    character_ids = _dedupe_preserve_order(character_ids)

    if location_id:
        location_id = _resolve_name_to_id(location_id, location_map) or location_id
    elif not location_id:
        location_id = str(shot.get("location_id") or "").strip() or None
        if location_id:
            location_id = _resolve_name_to_id(location_id, location_map) or location_id
    if not location_id:
        loc_names = list(assets_required.get("locations") or [])
        loc_name = str(shot.get("location") or shot.get("location_name") or "").strip()
        if loc_name:
            loc_names = loc_names or [loc_name]
        for name in loc_names:
            key = str(name).strip()
            if not key:
                continue
            location_id = _resolve_name_to_id(key, location_map) or key
            break

    return character_ids, location_id


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
    character_name_to_id = _load_character_name_to_id_map(project_paths)
    location_name_to_id = _load_location_name_to_id_map(project_paths)
    character_ids, location_id = _resolve_shot_asset_ids(
        shot, character_name_to_id, location_name_to_id
    )

    prompt = _build_keyframe_prompt(shot, override=prompt_override)
    if not prompt:
        raise ValueError("prompt_required")
    negative = _build_keyframe_negative(shot, override=negative_override)

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
    final_prompt = prompt
    attack_scene = _is_attack_action_scene(shot)
    multi_cast = len(stacked_character_ids) >= 2
    char_lora_strength: float | None = None
    max_char_lora: float | None = None
    if attack_scene and multi_cast:
        char_lora_strength = 0.35
    elif multi_cast:
        max_char_lora = 0.45
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
            character_look="minimal",
            prompt_order="scene_first",
            max_character_lora_strength=max_char_lora,
            character_lora_strength=char_lora_strength,
            settings=settings,
        )
        last_out = out
        final_prompt = str(out.get("prompt") or prompt)

        stem = next_candidate_stem(kpaths, shot_id)
        filename = f"{stem}.png"
        dest = kpaths.candidates_dir(shot_id) / filename
        shutil.copy2(Path(out["path"]), dest)

        created_at = datetime.now(timezone.utc).isoformat()
        sidecar = {
            "file": filename,
            "shot_id": shot_id,
            "prompt": final_prompt,
            "negative": negative,
            "loras": out.get("loras") or [],
            "created_at": created_at,
            "quality": {"status": "unchecked", "warnings": []},
        }
        _write_json(dest.with_suffix(".json"), sidecar)
        candidates.append({"file": filename, "url": ""})

    generation: dict[str, Any] = {
        "shot_id": shot_id,
        "prompt": final_prompt,
        "negative": negative,
        "character_ids": character_ids,
        "location_id": location_id,
        "use_location_lora": use_location_lora,
        "loras": (last_out or {}).get("loras") or [],
        "backend": _backend_name(backend),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "warnings": warnings,
        "prompt_order": "scene_first",
    }
    _write_json(kpaths.generation_json(shot_id), generation)

    return {
        "shot_id": shot_id,
        "status": "succeeded",
        "candidates": candidates,
        "warnings": warnings,
        "generation": generation,
    }
