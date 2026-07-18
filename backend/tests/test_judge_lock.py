from aivp.visual.judge import is_look_lock_eligible, normalize_judge_result


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
