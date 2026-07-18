from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import DEFAULT_LORA_WEIGHT, save_profile
from aivp.visual.trainset_check import check_trainset, _image_type


def _split_train_cmd(cmd: str) -> list[str]:
    """Split AIVP_LORA_TRAIN_CMD for subprocess.

    On Windows, ``shlex.split(..., posix=False)`` keeps surrounding quotes as
    part of each token, which makes ``python \"path\\to.py\"`` fail with
    Errno 22. Strip those quotes after splitting.
    """
    posix = os.name != "nt"
    argv = shlex.split(cmd, posix=posix)
    if not posix:
        cleaned: list[str] = []
        for arg in argv:
            if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'":
                cleaned.append(arg[1:-1])
            else:
                cleaned.append(arg)
        return cleaned
    return argv


def _caption_for(img: Path, profile: dict, source_folder: str) -> str:
    trigger = profile.get("trigger") or ""
    look = (profile.get("prompt_zh") or "").strip()
    name = img.name.lower()
    if "turnaround" in name:
        view = "front view" if "front" in name else (
            "side view" if "side" in name else ("back view" if "back" in name else "turnaround")
        )
        tag = f"{view}, character turnaround sheet"
    elif "expr_" in name or "expression" in name:
        tag = "character expression sheet"
    elif source_folder == "candidates":
        tag = "upper body portrait, character reference"
    else:
        tag = "character reference"
    parts = [trigger, look, tag, "guofeng anime", "consistent character design"]
    return ", ".join(p for p in parts if p)


def prepare_train_package(
    vpaths: VisualPaths,
    character_id: str,
    profile: dict,
    *,
    require_can_train: bool = False,
) -> dict[str, Any]:
    curated = sorted(vpaths.curated_dir(character_id).glob("*.png"))
    if not curated:
        raise FileNotFoundError(f"no_curated_images:{character_id}")

    quality = check_trainset(vpaths, character_id)
    if require_can_train and not quality.get("can_train"):
        raise ValueError(f"trainset_not_ready:{character_id}:{quality.get('warnings')}")

    lora_dir = vpaths.lora_dir(character_id)
    lora_dir.mkdir(parents=True, exist_ok=True)
    sources = profile.get("curated_sources") if isinstance(profile.get("curated_sources"), list) else []
    by_file = {str(s.get("file")): s for s in sources if isinstance(s, dict)}

    images: list[dict[str, Any]] = []
    trigger = profile.get("trigger") or character_id
    for img in curated:
        meta = by_file.get(img.name) or {}
        folder = str(meta.get("folder") or (
            "sheets" if "turnaround" in img.name or "expr_" in img.name else "candidates"
        ))
        cap = img.with_suffix(".txt")
        if not cap.exists() or not cap.read_text(encoding="utf-8").strip():
            text = _caption_for(img, profile, folder)
            cap.write_text(text, encoding="utf-8")
        else:
            text = cap.read_text(encoding="utf-8").strip()
            if trigger and trigger not in text:
                text = f"{trigger}, {text}"
                cap.write_text(text, encoding="utf-8")
        try:
            from PIL import Image  # type: ignore

            with Image.open(img) as im:
                width, height = im.size
        except Exception:  # noqa: BLE001
            width, height = 0, 0
        images.append(
            {
                "file": img.name,
                "caption_file": cap.name,
                "caption": text,
                "source_folder": folder,
                "image_type": _image_type(img.name),
                "selected_at": profile.get("curated_at") or "",
                "width": width,
                "height": height,
            }
        )

    output_name = f"{profile.get('trigger') or character_id}"
    dataset = {
        "schema_version": 2,
        "character_id": character_id,
        "name": profile.get("name") or character_id,
        "trigger": trigger,
        "base_model": "sdxl",
        "images": images,
        # Legacy flat fields for older trainers / tests.
        "resolution": 1024,
        "repeats": 10,
        "network_dim": 16,
        "network_alpha": 16,
        "learning_rate": "1e-4",
        "max_train_epochs": 10,
        "output_name": output_name,
        "output_dir": str(lora_dir),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "caption_note": "sheets+candidates; each png has matching .txt for LoRA",
        "training": {
            "resolution": 1024,
            "repeats": 10,
            "network_dim": 16,
            "network_alpha": 16,
            "learning_rate": "1e-4",
            "max_train_epochs": 10,
            "output_name": output_name,
            "output_dir": str(lora_dir),
        },
        "quality_check": {
            "image_count": quality["image_count"],
            "caption_count": quality["caption_count"],
            "has_front": quality["has_front"],
            "has_side": quality["has_side"],
            "has_back": quality["has_back"],
            "can_train": quality["can_train"],
            "score": quality["score"],
            "warnings": quality["warnings"],
        },
    }
    package = lora_dir / "train_package.json"
    package.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


def export_train_package(
    vpaths: VisualPaths,
    character_id: str,
    *,
    require_can_train: bool = True,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    dataset = prepare_train_package(
        vpaths, character_id, profile, require_can_train=require_can_train
    )
    profile["status"] = "package_ready"
    profile["train_status"] = "package_ready"
    profile["train_package"] = str(vpaths.lora_dir(character_id) / "train_package.json")
    profile["package_exported_at"] = datetime.now(timezone.utc).isoformat()
    save_profile(vpaths, profile)
    return {
        "character_id": character_id,
        "packaged": True,
        "dataset": dataset,
        "train_package": profile["train_package"],
    }


def execute_lora_train(
    vpaths: VisualPaths,
    character_id: str,
    settings,
    *,
    on_progress: Callable[[int, int, str | None], None] | None = None,
) -> dict[str, Any]:
    """Run external trainer (blocking). Caller handles async job wrapping."""
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    package_path = vpaths.lora_dir(character_id) / "train_package.json"
    if not package_path.exists():
        # Auto-export if missing (compat), but prefer explicit package step.
        prepare_train_package(vpaths, character_id, profile, require_can_train=True)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))

    cmd_tpl = getattr(settings, "lora_train_cmd", "") or ""
    result: dict[str, Any] = {
        "character_id": character_id,
        "trained": False,
        "command": None,
    }
    if not cmd_tpl:
        raise RuntimeError("lora_train_cmd_not_configured")

    profile["train_status"] = "training"
    profile["status"] = "training"
    profile["lora_ready"] = False
    save_profile(vpaths, profile)

    cmd = cmd_tpl.format(
        dataset_json=str(package_path),
        curated_dir=str(vpaths.curated_dir(character_id)),
        output_dir=str(vpaths.lora_dir(character_id)),
        trigger=profile.get("trigger") or "",
        character_id=character_id,
    )
    result["command"] = cmd
    argv = _split_train_cmd(cmd)
    stdout_path = vpaths.lora_dir(character_id) / "train_stdout.log"
    stderr_path = vpaths.lora_dir(character_id) / "train_stderr.log"
    if on_progress:
        on_progress(0, 1, "正在启动训练进程…")

    started = time.monotonic()
    proc = subprocess.Popen(
        argv,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _pump(stream, chunks: list[str]) -> None:
        if stream is None:
            return
        for line in stream:
            chunks.append(line)
            # Keep logs bounded in memory; full text still written at end via join.
            if len(chunks) > 20000:
                del chunks[:10000]

    t_out = threading.Thread(target=_pump, args=(proc.stdout, stdout_chunks), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, stderr_chunks), daemon=True)
    t_out.start()
    t_err.start()
    while proc.poll() is None:
        elapsed = int(time.monotonic() - started)
        if on_progress:
            on_progress(0, 1, f"LoRA 微调进行中… 已运行 {elapsed}s（请耐心等待，通常需数十分钟）")
        time.sleep(2.0)
    t_out.join(timeout=5)
    t_err.join(timeout=5)
    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    result["returncode"] = proc.returncode
    result["stdout"] = stdout_text[-2000:]
    result["stderr"] = stderr_text[-2000:]
    if on_progress:
        on_progress(1, 1, "训练进程已结束，正在检查输出…")

    loras = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    train_result = {
        "returncode": proc.returncode,
        "lora_files": [p.name for p in loras],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (vpaths.lora_dir(character_id) / "train_result.json").write_text(
        json.dumps(train_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if proc.returncode == 0 and loras:
        profile["status"] = "trained"
        profile["train_status"] = "trained"
        profile["probe_status"] = "pending"
        profile["lora_ready"] = False
        profile["lora_file"] = loras[0].name
        profile["lora_weight_default"] = float(
            profile.get("lora_weight_default") or DEFAULT_LORA_WEIGHT
        )
        profile["trained_at"] = datetime.now(timezone.utc).isoformat()
        profile.pop("train_error", None)
        result["trained"] = True
        result["lora_file"] = loras[0].name
    else:
        profile["status"] = "train_failed"
        profile["train_status"] = "failed"
        profile["lora_ready"] = False
        profile["train_error"] = result["stderr"] or f"exit:{proc.returncode}"
    save_profile(vpaths, profile)
    return result


def run_lora_train(
    vpaths: VisualPaths,
    character_id: str,
    settings,
) -> dict[str, Any]:
    """Backward-compatible entry: export package; train only if cmd configured."""
    packaged = export_train_package(vpaths, character_id, require_can_train=False)
    cmd_tpl = getattr(settings, "lora_train_cmd", "") or ""
    if not cmd_tpl:
        return {
            "character_id": character_id,
            "dataset": packaged["dataset"],
            "trained": False,
            "command": None,
            "message": (
                "train_package_written; set AIVP_LORA_TRAIN_CMD to run kohya/sd-scripts"
            ),
            "packaged": True,
        }
    trained = execute_lora_train(vpaths, character_id, settings)
    trained["dataset"] = packaged["dataset"]
    return trained
