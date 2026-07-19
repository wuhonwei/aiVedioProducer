from pathlib import Path

from aivp.visual.judge import is_look_lock_eligible, judge_image, normalize_judge_result


class _BadJsonVision:
    def complete_json_with_image(self, system, user, image_path, *, should_cancel=None):
        raise ValueError("ollama_vision_invalid_json: Expecting value")


class _MalformedVision:
    def complete_json_with_image(self, system, user, image_path, *, should_cancel=None):
        return "not-json-at-all"


def test_normalize_fails_half_body_tag():
    out = normalize_judge_result(
        {
            "pass": True,
            "score": 0.9,
            "checks": {
                "framing": {"pass": True, "note": "ok"},
                "clothing_covered": {"pass": True, "note": "ok"},
            },
            "failure_tags": ["half_body"],
        }
    )
    assert out["pass"] is False
    assert is_look_lock_eligible(out) is False


def test_lock_eligible_requires_pass_and_clean_tags():
    good = normalize_judge_result(
        {
            "pass": True,
            "score": 0.8,
            "checks": {
                "framing": {"pass": True, "note": "full"},
                "clothing_covered": {"pass": True, "note": "ok"},
                "outfit_complete": {"pass": True, "note": "ok"},
                "background_plain": {"pass": True, "note": "plain"},
                "gender": {"pass": True, "note": "ok"},
                "age": {"pass": True, "note": "ok"},
            },
            "failure_tags": [],
        }
    )
    assert good["pass"] is True
    assert is_look_lock_eligible(good) is True


def test_judge_image_falls_back_on_vision_json_error(tmp_path: Path):
    img = tmp_path / "cand_001.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    profile = {"name": "测试", "prompt_zh": "测试角色", "gender_presentation": "masculine"}
    out = judge_image(_BadJsonVision(), profile, img, slot_key="candidate")
    assert out["pass"] is True
    assert "vision_error" in out["summary"]
    assert is_look_lock_eligible(out) is True


def test_judge_image_falls_back_on_malformed_json_string(tmp_path: Path):
    img = tmp_path / "cand_002.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    profile = {"name": "测试", "prompt_zh": "测试角色", "gender_presentation": "masculine"}
    out = judge_image(_MalformedVision(), profile, img, slot_key="candidate")
    assert out["pass"] is True
    assert out["summary"] == "vision_bad_json"


def test_busy_background_check_fails_lock():
    bad = normalize_judge_result(
        {
            "pass": True,
            "score": 0.7,
            "checks": {
                "framing": {"pass": True, "note": "full"},
                "clothing_covered": {"pass": True, "note": "ok"},
                "background_plain": {"pass": False, "note": "forest"},
            },
            "failure_tags": [],
        }
    )
    assert bad["pass"] is False
    assert "busy_background" in bad["failure_tags"]
    assert is_look_lock_eligible(bad) is False
