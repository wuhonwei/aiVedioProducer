from aivp.llm.fake import FakeLlm
from aivp.visual.description_qa import (
    collect_entity_evidence,
    qa_character_description,
    wardrobe_grounded,
)


def test_wardrobe_grounded_when_cue_in_evidence():
    assert wardrobe_grounded("粗布家常衣衫", "开门的是白发苍苍的老婆婆，穿着粗布衣衫")
    assert not wardrobe_grounded("深蓝行囊式披风短衫", "白发苍苍的老婆婆坐在灶前")


def test_qa_passes_when_wardrobe_in_evidence():
    profile = {
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，粗布家常衣衫",
        "wardrobe": {"default": "粗布家常衣衫"},
    }
    entity = {"name": "苏婆婆", "evidence": "老婆婆穿着粗布衣衫，眼神温和"}
    out = qa_character_description(profile, entity)
    assert out["ok"] is True
    assert "description_needs_review" not in out["warnings"]


def test_qa_soft_passes_when_no_clothing_in_evidence():
    """Novel never describes clothes — keep inferred look, do not block bootstrap."""
    profile = {
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，锦绣华服",
        "wardrobe": {"default": "锦绣华服金丝披风"},
    }
    entity = {"name": "苏婆婆", "evidence": "白发苍苍的老婆婆坐在灶前烧水"}
    out = qa_character_description(profile, entity, llm=None, max_rewrites=2)
    assert out["ok"] is True
    assert "description_qa_wardrobe_ungrounded_soft" in out["warnings"]


def test_qa_soft_passes_inferred_wardrobe_even_if_evidence_has_other_clothes():
    profile = {
        "name": "林砚之",
        "prompt_zh": "林砚之，青灰布衣",
        "wardrobe": {"default": "青灰布衣与半旧蓝布包袱"},
        "inferred_fields": ["wardrobe.default", "prompt_zh"],
    }
    entity = {
        "name": "林砚之",
        "evidence": "林砚之背着一个半旧的蓝布包袱，站在雾里。",
    }
    out = qa_character_description(profile, entity, llm=None)
    assert out["ok"] is True
    assert "description_qa_inferred_wardrobe_allowed" in out["warnings"] or (
        "description_qa_wardrobe_ungrounded_soft" in out["warnings"]
    )


def test_qa_hard_fails_when_contradicts_evidence_and_not_inferred():
    profile = {
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，锦绣华服",
        "wardrobe": {"default": "锦绣华服金丝披风"},
        # deliberately not inferred — claimed as grounded but wrong
    }
    entity = {"name": "苏婆婆", "evidence": "白发苍苍的老婆婆，穿着粗布衣衫"}
    out = qa_character_description(profile, entity, llm=None, max_rewrites=2)
    assert out["ok"] is False
    assert "description_needs_review" in out["warnings"]


def test_qa_rewrites_with_llm_toward_evidence():
    profile = {
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，锦绣华服",
        "wardrobe": {"default": "锦绣华服"},
    }
    entity = {"name": "苏婆婆", "evidence": "白发苍苍的老婆婆，穿着粗布衣衫"}
    llm = FakeLlm(
        default={
            "wardrobe_default": "粗布家常衣衫",
            "prompt_zh": "苏婆婆，女性，花甲，身着粗布家常衣衫",
        }
    )
    out = qa_character_description(profile, entity, llm=llm, max_rewrites=2)
    assert out["ok"] is True
    assert out["rewrites"] >= 1
    assert "粗布" in out["profile"]["wardrobe"]["default"]


def test_collect_entity_evidence_joins_list():
    blob = collect_entity_evidence(
        {
            "evidence": "甲",
            "evidence_list": [{"text": "乙"}, "丙"],
            "aliases": ["丁"],
        }
    )
    assert "甲" in blob and "乙" in blob and "丙" in blob
