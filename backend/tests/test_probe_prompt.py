import json
from pathlib import Path

from aivp.visual.image_backend import StubImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile
from aivp.visual.t2i import (
    _probe_user_extra,
    default_probe_prompt,
    generate_with_character,
)


def _profile() -> dict:
    return {
        "id": "ent_0001",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "林砚之，男性，十七至二十二岁行旅青年，青灰布衣与半旧蓝布包袱",
        "gender_presentation": "masculine",
        "age_look": "十七至二十二岁行旅青年面相",
        "wardrobe": {"default": "青灰布衣与半旧蓝布包袱", "colors": ["青灰", "蓝"]},
        "consistency_anchors": ["青灰布衣与半旧蓝布包袱"],
    }


def test_default_probe_prompt_matches_training_style():
    p = {
        **_profile(),
        "trigger": "c6797781a4e4b_aivp",
        "character_id": "ent_0001",
    }
    text = default_probe_prompt(p)
    assert "c6797781a4e4b_aivp" in text
    assert "full body" in text
    assert "1boy" in text or "male" in text
    assert "guofeng anime style" in text
    assert "upper body portrait" not in text
    assert "人物半身特写" not in text


def test_legacy_half_body_ui_prompt_ignored():
    profile = _profile()
    legacy = (
        f"{profile['prompt_zh']}，solo, 1person, looking at viewer, "
        "upper body portrait, simple background, 人物半身特写"
    )
    assert _probe_user_extra(legacy, profile) == ""
    assert _probe_user_extra("soft morning light", profile) == "soft morning light"


def test_generate_probe_uses_strong_negative(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p_probe")
    vpaths.ensure()
    character = _profile()
    profile = ensure_profile(vpaths, character)
    # Fake a trained lora file so staging/basename can resolve.
    lora_dir = vpaths.lora_dir("ent_0001")
    lora_dir.mkdir(parents=True, exist_ok=True)
    (lora_dir / "c6797781a4e4b_aivp.safetensors").write_bytes(b"x")
    profile["lora_file"] = "c6797781a4e4b_aivp.safetensors"
    profile["train_status"] = "trained"
    vpaths.profile_json("ent_0001").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    legacy = (
        f"{profile['prompt_zh']}，solo, 1person, upper body portrait, 人物半身特写"
    )
    out = generate_with_character(
        vpaths,
        "ent_0001",
        legacy,
        StubImageBackend(),
        is_probe=True,
    )
    assert "full body" in out["prompt"]
    assert "face clearly visible" in out["prompt"]
    assert "人物半身特写" not in out["prompt"]
    assert "armor" in out["negative"] or "portrait crop" in out["negative"]
    assert float(out["lora_strength"]) >= 0.85
    assert Path(out["path"]).exists()


def test_generate_probe_uses_look_lock_when_present(tmp_path: Path):
    from PIL import Image

    from aivp.visual.look_lock import set_look_lock

    vpaths = VisualPaths(tmp_path, "p_probe_lock")
    vpaths.ensure()
    character = _profile()
    profile = ensure_profile(vpaths, character)
    cand_dir = vpaths.candidates_dir("ent_0001")
    cand_dir.mkdir(parents=True, exist_ok=True)
    src = cand_dir / "cand_lock.png"
    Image.new("RGB", (64, 96), color=(40, 80, 120)).save(src)
    set_look_lock(
        vpaths, "ent_0001", folder="candidates", filename="cand_lock.png"
    )
    lora_dir = vpaths.lora_dir("ent_0001")
    lora_dir.mkdir(parents=True, exist_ok=True)
    (lora_dir / "demo_aivp.safetensors").write_bytes(b"x")
    profile = json.loads(vpaths.profile_json("ent_0001").read_text(encoding="utf-8"))
    profile["lora_file"] = "demo_aivp.safetensors"
    profile["train_status"] = "trained"
    vpaths.profile_json("ent_0001").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    out = generate_with_character(
        vpaths,
        "ent_0001",
        "",
        StubImageBackend(),
        is_probe=True,
    )
    assert out["used_look_lock"] is True
    assert 0.50 <= float(out["denoise"]) <= 0.66
    assert float(out["lora_strength"]) == 0.75 or float(out["lora_strength"]) <= 0.85
    meta = json.loads(Path(out["path"]).with_suffix(".json").read_text(encoding="utf-8"))
    assert meta.get("ref_image")
    assert float(meta.get("denoise") or 1) < 0.999
