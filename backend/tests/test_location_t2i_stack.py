from pathlib import Path

from aivp.visual.image_backend import StubImageBackend, build_sdxl_txt2img_workflow
from aivp.visual.location_profiles import ensure_location_profile, save_location_profile
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, save_profile
from aivp.visual.t2i import generate_shot_with_loras


def test_workflow_chains_multiple_loras():
    wf = build_sdxl_txt2img_workflow(
        checkpoint="Guofeng4.2XL.safetensors",
        prompt="test",
        negative="bad",
        seed=1,
        loras=[
            {"name": "loc.safetensors", "strength": 0.7},
            {"name": "char.safetensors", "strength": 0.8},
        ],
    )
    assert wf["10"]["class_type"] == "LoraLoader"
    assert wf["10"]["inputs"]["lora_name"] == "loc.safetensors"
    assert wf["11"]["class_type"] == "LoraLoader"
    assert wf["11"]["inputs"]["lora_name"] == "char.safetensors"
    assert wf["11"]["inputs"]["model"] == ["10", 0]


def test_generate_shot_with_loras_records_stack(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {
        "id": "loc_1",
        "name": "渡口",
        "tier": "major",
        "prompt_zh": "青石渡口",
    }
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")

    out = generate_shot_with_loras(
        v,
        StubImageBackend(),
        prompt="立于埠头远望江雾",
        location_id="loc_1",
        character_ids=["ent_1"],
        shot_id="s1",
        use_location_lora=True,
    )
    assert Path(out["path"]).exists()
    assert len(out["loras"]) == 2
    assert out["loras"][0]["name"] == "dukou_loc.safetensors"
    assert out["loras"][1]["name"] == "lin_aivp.safetensors"
    meta = Path(out["path"]).with_suffix(".json")
    data = __import__("json").loads(meta.read_text(encoding="utf-8"))
    assert len(data.get("loras") or []) == 2
    assert "dukou" in (out.get("location_trigger") or "") or out["location_trigger"].endswith(
        "_loc_aivp"
    )


def test_generate_shot_skips_location_lora_by_default(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口"}
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    loc_p["trigger"] = "dukou_loc_aivp"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")

    out = generate_shot_with_loras(
        v,
        StubImageBackend(),
        prompt="立于埠头",
        location_id="loc_1",
        character_ids=["ent_1"],
        shot_id="s1",
    )
    assert out.get("use_location_lora") is False
    assert out["location_lora_file"] is None
    assert len(out["loras"]) == 1
    assert out["loras"][0]["name"] == "lin_aivp.safetensors"
    assert "dukou_loc_aivp" in out["prompt"] or "青石渡口" in out["prompt"]


def test_generate_shot_stacks_location_lora_when_enabled(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口"}
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")

    out = generate_shot_with_loras(
        v,
        StubImageBackend(),
        prompt="立于埠头",
        location_id="loc_1",
        character_ids=["ent_1"],
        shot_id="s1",
        use_location_lora=True,
    )
    assert out.get("use_location_lora") is True
    assert len(out["loras"]) == 2
    assert out["loras"][0]["name"] == "dukou_loc.safetensors"
    assert out["loras"][1]["name"] == "lin_aivp.safetensors"
    assert out["location_lora_file"] == "dukou_loc.safetensors"
