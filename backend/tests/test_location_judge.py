from aivp.visual.location_judge import is_location_look_lock_eligible


def test_eligible_requires_no_people():
    judged = {
        "pass": True,
        "score": 0.8,
        "checks": {
            "no_people": {"pass": False, "note": "face"},
            "place_readable": {"pass": True},
            "establishing_or_env": {"pass": True},
            "style_match": {"pass": True},
            "not_character_sheet": {"pass": True},
        },
        "failure_tags": ["has_people"],
    }
    assert is_location_look_lock_eligible(judged) is False


def test_eligible_ok():
    judged = {
        "pass": True,
        "score": 0.8,
        "checks": {
            "no_people": {"pass": True},
            "place_readable": {"pass": True},
            "establishing_or_env": {"pass": True},
            "style_match": {"pass": True},
            "not_character_sheet": {"pass": True},
        },
        "failure_tags": [],
    }
    assert is_location_look_lock_eligible(judged) is True
