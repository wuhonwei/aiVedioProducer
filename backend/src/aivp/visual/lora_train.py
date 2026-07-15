from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths


def prepare_train_package(vpaths: VisualPaths, character_id: str, profile: dict) -> dict[str, Any]:
    curated = list(vpaths.curated_dir(character_id).glob("*.png"))
    if not curated:
        raise FileNotFoundError(f"no_curated_images:{character_id}")
    lora_dir = vpaths.lora_dir(character_id)
    lora_dir.mkdir(parents=True, exist_ok=True)
    dataset = {
        "character_id": character_id,
        "trigger": profile.get("trigger"),
        "images": [p.name for p in curated],
        "resolution": 1024,
        "repeats": 10,
        "network_dim": 16,
        "network_alpha": 16,
        "learning_rate": "1e-4",
        "max_train_epochs": 10,
        "output_name": f"{profile.get('trigger') or character_id}",
        "output_dir": str(lora_dir),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    package = lora_dir / "train_package.json"
    package.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    # Caption check
    for img in curated:
        cap = img.with_suffix(".txt")
        if not cap.exists():
            cap.write_text(
                f"{profile.get('trigger')}, guofeng anime character",
                encoding="utf-8",
            )
    return dataset


def run_lora_train(
    vpaths: VisualPaths,
    character_id: str,
    settings,
) -> dict[str, Any]:
    profile_path = vpaths.profile_json(character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile_missing:{character_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    dataset = prepare_train_package(vpaths, character_id, profile)
    cmd_tpl = getattr(settings, "lora_train_cmd", "") or ""
    result: dict[str, Any] = {
        "character_id": character_id,
        "dataset": dataset,
        "trained": False,
        "command": None,
    }
    if not cmd_tpl:
        # No external trainer — mark package ready.
        profile["status"] = "train_package_ready"
        profile["train_package"] = str(vpaths.lora_dir(character_id) / "train_package.json")
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        result["message"] = (
            "train_package_written; set AIVP_LORA_TRAIN_CMD to run kohya/sd-scripts"
        )
        return result

    cmd = cmd_tpl.format(
        dataset_json=str(vpaths.lora_dir(character_id) / "train_package.json"),
        curated_dir=str(vpaths.curated_dir(character_id)),
        output_dir=str(vpaths.lora_dir(character_id)),
        trigger=profile.get("trigger") or "",
        character_id=character_id,
    )
    result["command"] = cmd
    argv = shlex.split(cmd, posix=False)
    proc = subprocess.run(argv, shell=False, capture_output=True, text=True, check=False)
    result["returncode"] = proc.returncode
    result["stdout"] = (proc.stdout or "")[-2000:]
    result["stderr"] = (proc.stderr or "")[-2000:]
    loras = list(vpaths.lora_dir(character_id).glob("*.safetensors"))
    if proc.returncode == 0 and loras:
        profile["status"] = "lora_ready"
        profile["lora_file"] = loras[0].name
        profile["trained_at"] = datetime.now(timezone.utc).isoformat()
        result["trained"] = True
        result["lora_file"] = loras[0].name
    else:
        profile["status"] = "train_failed"
        profile["train_error"] = result["stderr"] or f"exit:{proc.returncode}"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
