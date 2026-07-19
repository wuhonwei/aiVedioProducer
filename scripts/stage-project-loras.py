"""One-shot: stage all project character LoRAs into ComfyUI models/loras."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "src"))

from aivp.visual.lora_staging import default_comfy_loras_dir, stage_lora_file  # noqa: E402


def main() -> None:
    data = BACKEND / "data" / "projects"
    dest = default_comfy_loras_dir()
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for lora in data.glob("*/visual/characters/*/lora/*.safetensors"):
        if "_smoke" in str(lora):
            continue
        name = stage_lora_file(lora, dest)
        print(f"staged {name} <- {lora}")
        count += 1
    print(f"done: {count} file(s) -> {dest}")


if __name__ == "__main__":
    main()
