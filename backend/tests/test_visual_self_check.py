from collections import Counter
from pathlib import Path

from aivp.visual.judge import normalize_judge_result
from aivp.visual.self_check import suggest_patches, apply_suggested_patches, evaluate_character_images
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile
from aivp.visual.qa_tuning import load_qa_tuning


class FakeVision:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or {
            "pass": False,
            "score": 0.2,
            "summary": "bare chest",
            "checks": {
                "gender": {"pass": True, "note": "male"},
                "clothing_covered": {"pass": False, "note": "shirtless"},
                "outfit_match": {"pass": False, "note": "wrong"},
                "framing": {"pass": True, "note": "full body"},
                "view_angle": {"pass": True, "note": "front"},
            },
            "failure_tags": ["shirtless", "wrong_outfit"],
        }
        self.calls = 0

    def complete_json_with_image(self, system, user, image_path, *, should_cancel=None):
        self.calls += 1
        return dict(self.payload)


def test_normalize_judge_hard_fail_clothing():
    out = normalize_judge_result(
        {
            "pass": True,
            "score": 0.9,
            "checks": {"clothing_covered": {"pass": False, "note": "bare"}},
            "failure_tags": [],
        }
    )
    assert out["pass"] is False
    assert "shirtless_or_revealing" in out["failure_tags"]


def test_suggest_patches_for_shirtless():
    tags = Counter({"shirtless": 5, "wrong_outfit": 3})
    patches = suggest_patches(tags, pass_rate=0.2)
    assert patches.get("outfit_lock_boost") is True
    assert float(patches.get("candidate_denoise_hi") or 1) <= 0.70


def test_evaluate_character_images_with_fake_vision(tmp_path: Path):
    from PIL import Image

    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "深蓝披风短衫",
        "gender_presentation": "masculine",
        "wardrobe": {"default": "深蓝行囊式披风短衫"},
    }
    ensure_profile(vpaths, character)
    cand = vpaths.candidates_dir("ent_0001")
    cand.mkdir(parents=True, exist_ok=True)
    img = cand / "cand_001.png"
    Image.new("RGB", (64, 96), color=(20, 40, 80)).save(img)

    vision = FakeVision()
    report = evaluate_character_images(vpaths, character, vision, include_sheets=False)
    assert report["count"] == 1
    assert report["pass_count"] == 0
    assert vision.calls == 1
    assert "shirtless" in (report.get("failure_tags") or {})


def test_apply_suggested_patches_persists(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    patches = suggest_patches(Counter({"shirtless": 4}), pass_rate=0.1)
    apply_suggested_patches(vpaths, patches)
    loaded = load_qa_tuning(vpaths)
    assert loaded.get("outfit_lock_boost") is True
