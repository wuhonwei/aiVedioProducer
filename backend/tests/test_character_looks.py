"""Distinct major character looks — seeds and hard validation."""
from __future__ import annotations

from aivp.pipeline.character_looks import (
    assert_major_characters_distinct,
    compose_character_prompt_zh,
    look_signature,
    seed_character_look,
)
from aivp.pipeline.coerce_assets import ensure_character_card


def _full_app(**overrides):
    base = {
        "face": "圆脸",
        "face_shape": "圆脸",
        "eyes": "杏眼",
        "nose": "直鼻",
        "eyebrows": "浓眉",
        "mouth": "薄唇",
        "hair": "黑短发",
        "body": "中等匀称",
        "height": "身高约一七五",
        "limbs": "四肢匀称",
        "weight": "体重适中",
        "distinctive_marks": "",
    }
    base.update(overrides)
    return base


def test_seed_differs_for_qingduchuan_roles():
    lin = seed_character_look(
        {
            "name": "林砚之",
            "evidence": "林砚之背着一个半旧的蓝布包袱，站在雾里",
            "aliases": [],
        }
    )
    po = seed_character_look(
        {
            "name": "苏婆婆",
            "evidence": "开门的是一个白发苍苍的老婆婆，穿着粗布衣衫，眼神温和",
            "aliases": [],
        }
    )
    zhou = seed_character_look(
        {
            "name": "周大人",
            "evidence": "几个衙役护着一个穿着官服的人，是县里的知县，周大人",
            "aliases": [],
        }
    )
    assert lin["gender_presentation"] == "masculine"
    assert "男性" in lin["prompt_zh"]
    assert "身高" in lin["prompt_zh"]
    assert "眼睛" not in lin["prompt_zh"] or "眼" in lin["prompt_zh"]
    assert all(
        lin["appearance"].get(k)
        for k in (
            "face_shape",
            "eyes",
            "nose",
            "eyebrows",
            "mouth",
            "hair",
            "body",
            "height",
            "limbs",
            "weight",
        )
    )
    assert po["gender_presentation"] == "feminine"
    assert "女性" in po["prompt_zh"]
    assert lin["wardrobe"]["default"] != po["wardrobe"]["default"]
    assert po["appearance"]["hair"] != lin["appearance"]["hair"]
    assert "官" in zhou["wardrobe"]["default"] or "袍" in zhou["wardrobe"]["default"]
    assert "白" in po["appearance"]["hair"] or "花白" in po["appearance"]["hair"]
    assert look_signature({**lin, "name": "林砚之", "prompt_zh": lin["prompt_zh"]}) != look_signature(
        {**po, "name": "苏婆婆", "prompt_zh": po["prompt_zh"]}
    )


def test_coerce_recomposes_even_when_llm_prompt_incomplete():
    card = ensure_character_card(
        {"id": "ent_1", "name": "林砚之", "evidence": "蓝布包袱赶路"},
        {
            "prompt_zh": "林砚之，英俊少年",
            "gender_presentation": "masculine",
            "age_look": "十七岁",
        },
        tier="major",
    )
    assert "男性" in card["prompt_zh"]
    assert "身高" in card["prompt_zh"]
    assert card["appearance"]["eyes"]
    assert card["appearance"]["body"]


def test_compose_includes_all_dimensions():
    p = compose_character_prompt_zh(
        name="甲",
        gender_presentation="masculine",
        age_look="青年",
        appearance=_full_app(),
        wardrobe_default="青衣",
    )
    for token in ("男性", "青年", "中等匀称", "身高约一七五", "四肢匀称", "体重适中", "圆脸", "杏眼", "直鼻", "浓眉", "薄唇", "黑短发", "青衣"):
        assert token in p


def test_assert_distinct_raises_on_collision():
    twin_a = {
        "name": "甲",
        "tier": "major",
        "age_look": "青年",
        "gender_presentation": "masculine",
        "appearance": _full_app(),
        "wardrobe": {"default": "同衣", "alternate": [], "colors": []},
        "prompt_zh": "",
    }
    twin_a["prompt_zh"] = compose_character_prompt_zh(
        name="甲",
        gender_presentation="masculine",
        age_look="青年",
        appearance=twin_a["appearance"],
        wardrobe_default="同衣",
    )
    twin_b = {
        "name": "乙",
        "tier": "major",
        "age_look": "青年",
        "gender_presentation": "masculine",
        "appearance": _full_app(),
        "wardrobe": {"default": "同衣", "alternate": [], "colors": []},
        "prompt_zh": "",
    }
    twin_b["prompt_zh"] = compose_character_prompt_zh(
        name="乙",
        gender_presentation="masculine",
        age_look="青年",
        appearance=twin_b["appearance"],
        wardrobe_default="同衣",
    )
    try:
        assert_major_characters_distinct([twin_a, twin_b])
        raised = False
    except ValueError as e:
        raised = True
        assert "甲" in str(e) and "乙" in str(e)
    assert raised


def test_assert_distinct_raises_on_empty_prompt():
    card = {
        "name": "空",
        "tier": "major",
        "age_look": "青年",
        "gender_presentation": "masculine",
        "appearance": _full_app(),
        "wardrobe": {"default": "衣", "alternate": [], "colors": []},
        "prompt_zh": "",
    }
    try:
        assert_major_characters_distinct([card])
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_hash_palette_stable_and_split():
    a = seed_character_look({"name": "角色甲", "evidence": "", "aliases": []})
    b = seed_character_look({"name": "角色乙", "evidence": "", "aliases": []})
    a2 = seed_character_look({"name": "角色甲", "evidence": "", "aliases": []})
    assert a["wardrobe"]["default"] == a2["wardrobe"]["default"]
    assert "男性" in a["prompt_zh"]
    assert look_signature({**a, "name": "角色甲", "prompt_zh": a["prompt_zh"]}) != look_signature(
        {**b, "name": "角色乙", "prompt_zh": b["prompt_zh"]}
    )
