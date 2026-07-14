from aivp.bible.overlay import merge_bible, apply_merge_patch, unset_path


def test_merge_overlay_wins():
    auto = {"logline": "自动", "characters": []}
    overlay = {"logline": "人工"}
    assert merge_bible(auto, overlay)["logline"] == "人工"


def test_apply_merge_patch_and_unset():
    overlay: dict = {}
    overlay = apply_merge_patch(overlay, {"logline": "改"})
    assert overlay["logline"] == "改"
    overlay = unset_path(overlay, "/logline")
    assert "logline" not in overlay
