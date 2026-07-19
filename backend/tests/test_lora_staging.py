from pathlib import Path

from aivp.visual.lora_staging import (
    default_comfy_loras_dir,
    resolve_comfy_loras_dir,
    stage_lora_file,
    stage_project_lora,
)


def test_default_comfy_loras_dir_points_at_tools_comfy():
    path = default_comfy_loras_dir()
    assert path.parts[-3:] == ("ComfyUI", "models", "loras")
    assert "tools" in path.parts


def test_stage_lora_file_hardlinks_or_copies(tmp_path: Path):
    src_dir = tmp_path / "project_lora"
    src_dir.mkdir()
    src = src_dir / "c6797781a4e4b_aivp.safetensors"
    src.write_bytes(b"fake-lora-weights")
    dest_dir = tmp_path / "comfy_loras"

    name = stage_lora_file(src, dest_dir)
    assert name == "c6797781a4e4b_aivp.safetensors"
    dest = dest_dir / name
    assert dest.is_file()
    assert dest.read_bytes() == b"fake-lora-weights"

    # Second call is idempotent.
    name2 = stage_lora_file(src, dest_dir)
    assert name2 == name


def test_stage_project_lora_uses_settings_override(tmp_path: Path):
    src_dir = tmp_path / "char_lora"
    src_dir.mkdir()
    (src_dir / "demo_aivp.safetensors").write_bytes(b"x")
    dest_dir = tmp_path / "loras"

    class _S:
        comfy_loras_dir = dest_dir

    out = stage_project_lora(src_dir, "demo_aivp.safetensors", settings=_S())
    assert out == "demo_aivp.safetensors"
    assert (dest_dir / out).read_bytes() == b"x"
    assert resolve_comfy_loras_dir(_S()) == dest_dir
