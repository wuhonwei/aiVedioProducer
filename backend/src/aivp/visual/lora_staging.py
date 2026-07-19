"""Stage project LoRA weights into ComfyUI models/loras for LoraLoader."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def default_comfy_loras_dir() -> Path:
    """Repo-relative tools/ComfyUI/models/loras (backend/src/aivp/visual → repo)."""
    return Path(__file__).resolve().parents[4] / "tools" / "ComfyUI" / "models" / "loras"


def resolve_comfy_loras_dir(settings=None, override: Path | str | None = None) -> Path:
    if override is not None and str(override).strip():
        return Path(override)
    if settings is not None:
        configured = getattr(settings, "comfy_loras_dir", None)
        if configured is not None and str(configured).strip():
            return Path(configured)
    return default_comfy_loras_dir()


def stage_lora_file(source: Path, loras_dir: Path) -> str:
    """Hardlink (or copy) source into Comfy loras dir; return basename for LoraLoader."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"lora_missing:{source}")
    loras_dir = Path(loras_dir)
    loras_dir.mkdir(parents=True, exist_ok=True)
    dest = loras_dir / source.name
    if dest.exists():
        try:
            if dest.samefile(source):
                return dest.name
        except OSError:
            pass
        if dest.stat().st_size == source.stat().st_size:
            return dest.name
        dest.unlink()
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy2(source, dest)
    return dest.name


def stage_project_lora(
    source_dir: Path,
    basename: str,
    *,
    settings=None,
    comfy_loras_dir: Path | str | None = None,
) -> str:
    """Stage `{source_dir}/{basename}` into Comfy loras; return basename."""
    name = Path(basename).name
    return stage_lora_file(
        Path(source_dir) / name,
        resolve_comfy_loras_dir(settings, comfy_loras_dir),
    )
