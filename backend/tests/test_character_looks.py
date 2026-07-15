"""Distinct major character looks — seeds and hard validation."""
from __future__ import annotations

import hashlib
import re

from aivp.pipeline.character_looks import (
    assert_major_characters_distinct,
    look_signature,
    seed_character_look,
)


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
    assert lin["wardrobe"]["default"] != po["wardrobe"]["default"]
    assert po["appearance"]["hair"] != lin["appearance"]["hair"]
    assert "官" in zhou["wardrobe"]["default"] or "袍" in zhou["wardrobe"]["default"]
    assert "白" in po["appearance"]["hair"] or "花白" in po["appearance"]["hair"]
    assert look_signature({**lin, "name": "林砚之", "prompt_zh": lin["prompt_zh"]}) != look_signature(
        {**po, "name": "苏婆婆", "prompt_zh": po["prompt_zh"]}
    )


def test_assert_distinct_raises_on_collision():
    twin_a = {
        "name": "甲",
        "tier": "major",
        "age_look": "青年",
        "appearance": {"face": "同脸", "hair": "同发", "body": "", "distinctive_marks": ""},
        "wardrobe": {"default": "同衣", "alternate": [], "colors": []},
        "prompt_zh": "甲，青年，同发，同脸，身着同衣",
    }
    twin_b = {
        "name": "乙",
        "tier": "major",
        "age_look": "青年",
        "appearance": {"face": "同脸", "hair": "同发", "body": "", "distinctive_marks": ""},
        "wardrobe": {"default": "同衣", "alternate": [], "colors": []},
        "prompt_zh": "乙，青年，同发，同脸，身着同衣",
    }
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
        "appearance": {"face": "面", "hair": "发", "body": "", "distinctive_marks": ""},
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
    # Different names should usually pick different palette slots
    assert look_signature({**a, "name": "角色甲", "prompt_zh": a["prompt_zh"]}) != look_signature(
        {**b, "name": "角色乙", "prompt_zh": b["prompt_zh"]}
    )
