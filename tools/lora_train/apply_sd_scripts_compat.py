"""Apply local sd-scripts patches for transformers>=5 + offline tokenizer cache.

tools/sd-scripts is gitignored; re-run this whenever that tree is refreshed.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SD_SCRIPTS = Path(
    __import__("os").environ.get("AIVP_SD_SCRIPTS_ROOT")
    or (REPO_ROOT / "tools" / "sd-scripts")
)

TE1_MARKER = "transformers>=5: CLIPTextModel is flat"
TE1_NEEDLE = '''    if "text_model.embeddings.position_ids" in te1_sd:
        te1_sd.pop("text_model.embeddings.position_ids")

    info1 = _load_state_dict_on_device(text_model1, te1_sd, device=map_location)  # remain fp32
'''
TE1_REPL = '''    if "text_model.embeddings.position_ids" in te1_sd:
        te1_sd.pop("text_model.embeddings.position_ids")

    # transformers>=5: CLIPTextModel is flat (no nested .text_model); checkpoint keys still use text_model.*
    if not hasattr(text_model1, "text_model"):
        te1_sd = {
            (k[len("text_model.") :] if k.startswith("text_model.") else k): v
            for k, v in te1_sd.items()
        }

    info1 = _load_state_dict_on_device(text_model1, te1_sd, device=map_location)  # remain fp32
'''

GRAD_NEEDLE = '''    def prepare_text_encoder_grad_ckpt_workaround(self, index, text_encoder):
        # set top parameter requires_grad = True for gradient checkpointing works
        text_encoder.text_model.embeddings.requires_grad_(True)

    def prepare_text_encoder_fp8(self, index, text_encoder, te_weight_dtype, weight_dtype):
        text_encoder.text_model.embeddings.to(dtype=weight_dtype)
'''
GRAD_REPL = '''    def prepare_text_encoder_grad_ckpt_workaround(self, index, text_encoder):
        # set top parameter requires_grad = True for gradient checkpointing works
        # transformers>=5 CLIPTextModel is flat (no nested .text_model)
        emb = (
            text_encoder.text_model.embeddings
            if hasattr(text_encoder, "text_model")
            else text_encoder.embeddings
        )
        emb.requires_grad_(True)

    def prepare_text_encoder_fp8(self, index, text_encoder, te_weight_dtype, weight_dtype):
        emb = (
            text_encoder.text_model.embeddings
            if hasattr(text_encoder, "text_model")
            else text_encoder.embeddings
        )
        emb.to(dtype=weight_dtype)
'''


def apply() -> list[str]:
    done: list[str] = []
    model_util = SD_SCRIPTS / "library" / "sdxl_model_util.py"
    train_network = SD_SCRIPTS / "train_network.py"
    if not model_util.exists() or not train_network.exists():
        raise FileNotFoundError(f"sd-scripts_missing:{SD_SCRIPTS}")

    text = model_util.read_text(encoding="utf-8")
    if TE1_MARKER not in text:
        if TE1_NEEDLE not in text:
            raise RuntimeError("sdxl_model_util_patch_target_missing")
        model_util.write_text(text.replace(TE1_NEEDLE, TE1_REPL, 1), encoding="utf-8")
        done.append(str(model_util))

    text = train_network.read_text(encoding="utf-8")
    if "transformers>=5 CLIPTextModel is flat" not in text:
        if GRAD_NEEDLE not in text:
            # already patched with slightly different wording, or upstream changed
            if "hasattr(text_encoder, \"text_model\")" not in text:
                raise RuntimeError("train_network_patch_target_missing")
        else:
            train_network.write_text(text.replace(GRAD_NEEDLE, GRAD_REPL, 1), encoding="utf-8")
            done.append(str(train_network))
    return done


if __name__ == "__main__":
    applied = apply()
    print("applied:", applied or "already up to date")
