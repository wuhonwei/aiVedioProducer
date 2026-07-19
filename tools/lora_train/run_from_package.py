#!/usr/bin/env python3
"""Run SDXL character LoRA training from an AIVP train_package.json.

Invoked by AIVP_LORA_TRAIN_CMD with placeholders:
  {dataset_json} {curated_dir} {output_dir} {trigger} {character_id}

Uses tools/sd-scripts (kohya) + tools/ComfyUI/.venv (torch+CUDA).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SD_SCRIPTS = Path(os.environ.get("AIVP_SD_SCRIPTS_ROOT") or (REPO_ROOT / "tools" / "sd-scripts"))
COMFY_VENV_PY = REPO_ROOT / "tools" / "ComfyUI" / ".venv" / "Scripts" / "python.exe"
DEFAULT_CKPT = REPO_ROOT / "tools" / "ComfyUI" / "models" / "checkpoints" / "Guofeng4.2XL.safetensors"
TOKENIZER_CACHE = Path(
    os.environ.get("AIVP_TOKENIZER_CACHE_DIR")
    or (REPO_ROOT / "tools" / "lora_train" / "tokenizer_cache")
)
TOKENIZER_SPECS = (
    ("openai/clip-vit-large-patch14", "openai_clip-vit-large-patch14"),
    ("laion/CLIP-ViT-bigG-14-laion2B-39B-b160k", "laion_CLIP-ViT-bigG-14-laion2B-39B-b160k"),
)


def _safe_folder_token(trigger: str, character_id: str) -> str:
    raw = (trigger or character_id or "char").strip()
    cleaned = re.sub(r"[^\w\-]+", "_", raw, flags=re.UNICODE).strip("_")
    return (cleaned or "char")[:80]


def _resolve_python() -> Path:
    env_py = os.environ.get("AIVP_LORA_TRAIN_PYTHON", "").strip()
    if env_py:
        return Path(env_py)
    if COMFY_VENV_PY.exists():
        return COMFY_VENV_PY
    return Path(sys.executable)


def _resolve_checkpoint(package: dict) -> Path:
    env_ckpt = os.environ.get("AIVP_LORA_BASE_CHECKPOINT", "").strip()
    if env_ckpt:
        p = Path(env_ckpt)
        if p.exists():
            return p
    name = os.environ.get("AIVP_COMFY_CHECKPOINT", "").strip() or "Guofeng4.2XL.safetensors"
    cand = REPO_ROOT / "tools" / "ComfyUI" / "models" / "checkpoints" / name
    if cand.exists():
        return cand
    if DEFAULT_CKPT.exists():
        return DEFAULT_CKPT
    raise FileNotFoundError(
        "base_checkpoint_missing: set AIVP_LORA_BASE_CHECKPOINT or place "
        f"{name} under tools/ComfyUI/models/checkpoints/"
    )


def _tokenizer_ready(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    # transformers can load from tokenizer.json alone; accept either layout.
    names = {p.name for p in folder.iterdir()}
    return "tokenizer.json" in names or ("vocab.json" in names and "merges.txt" in names)


def ensure_tokenizer_cache(cache_dir: Path = TOKENIZER_CACHE) -> Path:
    """Ensure kohya SDXL CLIP tokenizers exist locally (HuggingFace often blocked)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [
        (model_id, folder)
        for model_id, folder in TOKENIZER_SPECS
        if not _tokenizer_ready(cache_dir / folder)
    ]
    if not missing:
        return cache_dir

    # Prefer China-friendly mirror when fetching once.
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from transformers import CLIPTokenizer  # lazy: only when download needed

    for model_id, folder in missing:
        dest = cache_dir / folder
        print(f"downloading tokenizer {model_id} -> {dest}", flush=True)
        tok = CLIPTokenizer.from_pretrained(model_id)
        dest.mkdir(parents=True, exist_ok=True)
        tok.save_pretrained(dest)
        if not _tokenizer_ready(dest):
            raise RuntimeError(f"tokenizer_cache_incomplete:{dest}")
    return cache_dir


def _prepare_kohya_dataset(
    curated_dir: Path,
    output_dir: Path,
    *,
    repeats: int,
    trigger: str,
    character_id: str,
) -> Path:
    """Kohya expects train_data_dir/<repeats>_<token>/*.png + matching .txt."""
    if not curated_dir.is_dir():
        raise FileNotFoundError(f"curated_dir_missing:{curated_dir}")
    images = sorted(curated_dir.glob("*.png"))
    if not images:
        raise FileNotFoundError(f"no_png_in_curated:{curated_dir}")

    token = _safe_folder_token(trigger, character_id)
    dataset_root = output_dir / "_kohya_dataset"
    bucket = dataset_root / f"{max(int(repeats), 1)}_{token}"
    if bucket.exists():
        shutil.rmtree(bucket)
    bucket.mkdir(parents=True, exist_ok=True)

    for img in images:
        dest_img = bucket / img.name
        shutil.copy2(img, dest_img)
        cap = img.with_suffix(".txt")
        dest_cap = bucket / f"{img.stem}.txt"
        if cap.exists():
            shutil.copy2(cap, dest_cap)
        else:
            dest_cap.write_text((trigger or token).strip() + "\n", encoding="utf-8")
    return dataset_root


def main() -> int:
    parser = argparse.ArgumentParser(description="AIVP SDXL LoRA train from package")
    parser.add_argument("--dataset-json", required=True)
    parser.add_argument("--curated-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--trigger", default="")
    parser.add_argument("--character-id", default="")
    parser.add_argument(
        "--max-train-epochs",
        type=int,
        default=None,
        help="Override package max_train_epochs (for smoke tests)",
    )
    args = parser.parse_args()

    package_path = Path(args.dataset_json).resolve()
    curated_dir = Path(args.curated_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not package_path.exists():
        print(f"ERROR: dataset json missing: {package_path}", file=sys.stderr)
        return 2
    if not (SD_SCRIPTS / "sdxl_train_network.py").exists():
        print(
            f"ERROR: sd-scripts missing at {SD_SCRIPTS}. "
            "Download kohya-ss/sd-scripts into tools/sd-scripts.",
            file=sys.stderr,
        )
        return 2

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from apply_sd_scripts_compat import apply as apply_compat

        applied = apply_compat()
        if applied:
            print("applied sd-scripts compat patches:", applied, flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: sd-scripts compat patch skipped: {exc}", flush=True)

    package = json.loads(package_path.read_text(encoding="utf-8"))
    training = package.get("training") if isinstance(package.get("training"), dict) else {}
    repeats = int(training.get("repeats") or package.get("repeats") or 10)
    resolution = int(training.get("resolution") or package.get("resolution") or 1024)
    network_dim = int(training.get("network_dim") or package.get("network_dim") or 16)
    network_alpha = int(training.get("network_alpha") or package.get("network_alpha") or 16)
    learning_rate = str(training.get("learning_rate") or package.get("learning_rate") or "1e-4")
    max_epochs = int(
        args.max_train_epochs
        if args.max_train_epochs is not None
        else (training.get("max_train_epochs") or package.get("max_train_epochs") or 10)
    )
    env_epochs = os.environ.get("AIVP_LORA_TRAIN_MAX_EPOCHS", "").strip()
    if args.max_train_epochs is None and env_epochs.isdigit():
        max_epochs = int(env_epochs)
    output_name = str(
        training.get("output_name")
        or package.get("output_name")
        or args.trigger
        or args.character_id
        or "character_lora"
    )
    trigger = str(args.trigger or package.get("trigger") or "")

    tokenizer_cache = ensure_tokenizer_cache(TOKENIZER_CACHE)
    dataset_root = _prepare_kohya_dataset(
        curated_dir,
        output_dir,
        repeats=repeats,
        trigger=trigger,
        character_id=args.character_id,
    )
    checkpoint = _resolve_checkpoint(package)
    python = _resolve_python()
    train_script = SD_SCRIPTS / "sdxl_train_network.py"

    cmd = [
        str(python),
        str(train_script),
        f"--pretrained_model_name_or_path={checkpoint}",
        f"--train_data_dir={dataset_root}",
        f"--output_dir={output_dir}",
        f"--output_name={output_name}",
        "--save_model_as=safetensors",
        f"--resolution={resolution}",
        "--train_batch_size=1",
        f"--max_train_epochs={max_epochs}",
        f"--network_dim={network_dim}",
        f"--network_alpha={network_alpha}",
        f"--learning_rate={learning_rate}",
        "--network_module=networks.lora",
        "--mixed_precision=fp16",
        "--save_every_n_epochs=999",
        "--caption_extension=.txt",
        "--cache_latents",
        "--cache_latents_to_disk",
        "--optimizer_type=AdamW",
        "--lr_scheduler=cosine",
        "--max_data_loader_n_workers=0",
        "--seed=42",
        "--gradient_checkpointing",
        "--no_half_vae",
        f"--tokenizer_cache_dir={tokenizer_cache}",
    ]

    print("AIVP LoRA train starting", flush=True)
    print("checkpoint:", checkpoint, flush=True)
    print("tokenizer_cache:", tokenizer_cache, flush=True)
    print("dataset:", dataset_root, flush=True)
    print("output:", output_dir / f"{output_name}.safetensors", flush=True)
    print("cmd:", " ".join(cmd), flush=True)

    env = os.environ.copy()
    # Ensure kohya library/ and networks/ resolve when launched by absolute script path.
    sep = os.pathsep
    env["PYTHONPATH"] = str(SD_SCRIPTS) + (
        sep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    # Avoid HuggingFace hub calls during train once tokenizers are cached.
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    proc = subprocess.run(cmd, cwd=str(SD_SCRIPTS), env=env)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
