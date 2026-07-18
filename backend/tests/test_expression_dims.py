"""Tests for story-driven expression dimension clustering."""

from aivp.bible.expression_dims import (
    build_expression_dims,
    framing_for_key,
    merge_expression_dims,
    normalize_emotion,
)


def test_normalize_emotion_synonyms():
    assert normalize_emotion("震惊、好奇") == "shocked"
    assert normalize_emotion("愤怒、决心") == "angry"
    assert normalize_emotion("关心、温暖") == "warm_care"
    assert normalize_emotion("平静、坚定") == "calm"
    # Specific pain cue maps to its own dim, not the legacy smile/happy set.
    assert normalize_emotion("咬牙忍痛") == "gritted_pain"
    custom = normalize_emotion("某种从未见过的情绪XYZ")
    assert custom.startswith("custom_")
    assert custom not in {"smile", "happy", "shy", "confused", "angry"}


def test_build_expression_dims_clusters_and_keeps_calm():
    character = {
        "id": "ent_0004",
        "name": "苏婆婆",
        "aliases": ["老婆婆"],
    }
    events = [
        {
            "id": "e1",
            "summary": "苏婆婆看见受伤的林砚之，吓了一跳",
            "emotion": "震惊、好奇",
            "cast": ["苏婆婆", "林砚之"],
        },
        {
            "id": "e2",
            "summary": "苏婆婆关心照顾林砚之",
            "emotion": "关心、温暖",
            "cast": ["苏婆婆"],
        },
        {
            "id": "e3",
            "summary": "无关事件",
            "emotion": "愤怒、决心",
            "cast": ["林砚之"],
        },
    ]
    dims = build_expression_dims(character, events)
    ids = [d["id"] for d in dims]
    assert "expr_calm" in ids
    assert "expr_shocked" in ids
    assert "expr_warm_care" in ids
    assert "expr_angry" not in ids  # other character's anger
    shocked = next(d for d in dims if d["id"] == "expr_shocked")
    assert shocked["evidence"]
    assert shocked["status"] == "proposed"
    calm = next(d for d in dims if d["id"] == "expr_calm")
    assert calm["status"] == "approved"
    assert framing_for_key("shocked")
    assert "face" in framing_for_key("shocked").lower() or "expression" in framing_for_key("shocked").lower()


def test_merge_expression_dims_preserves_approved_and_marks_stale():
    existing = [
        {
            "id": "expr_calm",
            "label": "平静",
            "emotion": "平静",
            "framing": "calm",
            "evidence": [],
            "priority": 1,
            "status": "approved",
        },
        {
            "id": "expr_angry",
            "label": "愤怒",
            "emotion": "愤怒",
            "framing": "angry",
            "evidence": [{"text": "old", "source": "events", "ref": "old"}],
            "priority": 2,
            "status": "approved",
        },
    ]
    incoming = [
        {
            "id": "expr_calm",
            "label": "平静",
            "emotion": "平静",
            "framing": "calm new",
            "evidence": [],
            "priority": 1,
            "status": "approved",
        },
        {
            "id": "expr_shocked",
            "label": "震惊",
            "emotion": "震惊",
            "framing": "shocked",
            "evidence": [{"text": "吓了一跳", "source": "events", "ref": "e1"}],
            "priority": 2,
            "status": "proposed",
        },
    ]
    merged = merge_expression_dims(existing, incoming)
    by_id = {d["id"]: d for d in merged}
    assert by_id["expr_angry"]["status"] == "stale"
    assert by_id["expr_angry"]["status"] != "rejected"
    assert by_id["expr_shocked"]["status"] == "proposed"
    assert by_id["expr_calm"]["status"] == "approved"
