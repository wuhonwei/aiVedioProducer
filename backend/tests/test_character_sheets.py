from pathlib import Path

import json

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths
from aivp.visual.image_backend import StubImageBackend, build_sdxl_txt2img_workflow
from aivp.visual.paths import VisualPaths
from aivp.visual.prompts import EXPRESSION_SLOTS, PROBE_FRAMING, TURNAROUND_SLOTS
from aivp.visual.sheets import generate_character_sheets


class FakeLlm:
    def __init__(self, default=None):
        self.default = default or {}

    def complete_json(self, *args, **kwargs):
        return self.default


def test_workflow_portrait_size_and_lora():
    wf = build_sdxl_txt2img_workflow(
        checkpoint="Guofeng4.2XL.safetensors",
        prompt="lin_aivp, boy",
        negative="blurry",
        seed=1,
        width=768,
        height=1024,
        lora_name="char.safetensors",
        lora_strength=0.75,
    )
    assert wf["5"]["inputs"]["width"] == 768
    assert wf["5"]["inputs"]["height"] == 1024
    assert wf["10"]["class_type"] == "LoraLoader"
    assert wf["10"]["inputs"]["lora_name"] == "char.safetensors"
    assert wf["3"]["inputs"]["model"] == ["10", 0]
    assert wf["6"]["inputs"]["clip"] == ["10", 1]


def test_resolve_sheet_slots_groups():
    from aivp.visual.sheets import resolve_sheet_slots

    assert len(resolve_sheet_slots(group="turnaround")) == 3
    assert len(resolve_sheet_slots(group="expression")) == 8
    assert len(resolve_sheet_slots(slot_keys=["expr_happy"])) == 1
    assert resolve_sheet_slots(slot_keys=["expr_happy"])[0][0] == "expr_happy"


def test_generate_character_sheets_stub(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林启之",
        "tier": "major",
        "prompt_zh": "青灰长衫少年",
    }
    out = generate_character_sheets(
        vpaths, character, StubImageBackend(), group="turnaround"
    )
    assert len(out["files"]) == 3
    front = [f for f in out["files"] if f["key"] == "turnaround_front"]
    assert front and (vpaths.sheets_dir("ent_0001") / front[0]["file"]).exists()
    # Second click appends more files (no overwrite)
    again = generate_character_sheets(
        vpaths, character, StubImageBackend(), group="turnaround"
    )
    assert len(again["files"]) == 3
    pngs = list(vpaths.sheets_dir("ent_0001").glob("sheet_turnaround_*.png"))
    assert len(pngs) >= 6
    one = generate_character_sheets(
        vpaths,
        character,
        StubImageBackend(),
        slot_keys=["expr_confused"],
    )
    assert len(one["files"]) == 1
    assert one["files"][0]["key"] == "expr_confused"
    assert (vpaths.sheets_dir("ent_0001") / one["files"][0]["file"]).exists()
    all_out = generate_character_sheets(vpaths, character, StubImageBackend())
    expected = len(TURNAROUND_SLOTS) + len(EXPRESSION_SLOTS)
    assert len(all_out["files"]) == expected
    happy = [f for f in all_out["files"] if f["key"] == "expr_happy"]
    assert happy


def test_visual_sheets_and_delete_api(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'v.db'}", image_backend="stub")
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "视觉表"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "id": "ent_0001",
                        "name": "林启之",
                        "tier": "major",
                        "prompt_zh": "青灰长衫少年",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    job = client.post(
        f"/api/projects/{pid}/visual/sheets",
        json={"character_id": "ent_0001"},
    )
    assert job.status_code == 202
    jid = job.json()["id"]
    status = client.get(f"/api/projects/{pid}/visual/jobs/{jid}")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"

    listed = client.get(f"/api/projects/{pid}/visual/characters")
    assert listed.status_code == 200
    ch = listed.json()["characters"][0]
    assert ch["sheet_count"] >= 3
    fname = ch["sheets"][0]
    got = client.get(f"/api/projects/{pid}/visual/characters/ent_0001/files/sheets/{fname}")
    assert got.status_code == 200
    deleted = client.delete(
        f"/api/projects/{pid}/visual/characters/ent_0001/files/sheets/{fname}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    missing = client.get(
        f"/api/projects/{pid}/visual/characters/ent_0001/files/sheets/{fname}"
    )
    assert missing.status_code == 404


def test_turnaround_side_back_skip_look_lock_image():
    from aivp.visual.look_lock import sheet_cfg_for, sheet_denoise_for, sheet_uses_look_lock_image

    assert sheet_uses_look_lock_image("turnaround_front") is True
    assert sheet_uses_look_lock_image("expr_calm") is True
    # Side/back must be txt2img — front look-lock latent keeps front pose.
    assert sheet_uses_look_lock_image("turnaround_side") is False
    assert sheet_uses_look_lock_image("turnaround_back") is False
    # Strong emotions still use face_ref for framing, but with near-txt2img denoise.
    assert sheet_uses_look_lock_image("expr_angry") is True
    assert sheet_denoise_for("turnaround_side", 0.55) >= 0.88
    assert sheet_denoise_for("turnaround_back", 0.55) >= 0.88
    assert sheet_cfg_for("turnaround_side") >= 9.0
    assert sheet_denoise_for("expr_smile", 0.55) >= 0.68
    assert sheet_denoise_for("expr_angry", 0.55) >= 0.88
    assert sheet_cfg_for("expr_angry") >= 12.0
    for key, _label, framing in TURNAROUND_SLOTS:
        if key == "turnaround_side":
            low = framing.lower()
            assert "side" in low and "profile" in low
            assert "front face" in low or "no three-quarter" in low
        if key == "turnaround_back":
            low = framing.lower()
            assert "rear" in low or "behind" in low
            assert "no face" in low


def test_resolve_sheet_slots_uses_bible_expression_dims():
    from aivp.visual.sheets import resolve_sheet_slots

    dims = [
        {
            "id": "expr_calm",
            "label": "平静",
            "framing": "calm neutral face",
            "status": "approved",
        },
        {
            "id": "expr_shocked",
            "label": "震惊",
            "framing": "shocked wide eyes",
            "status": "proposed",
        },
        {
            "id": "expr_angry",
            "label": "愤怒",
            "framing": "angry",
            "status": "stale",
        },
    ]
    slots = resolve_sheet_slots(group="expression", expression_dims=dims)
    ids = [s[0] for s in slots]
    assert ids == ["expr_calm", "expr_shocked"]
    assert "shocked" in slots[1][2]


def test_resolve_sheet_slots_falls_back_to_legacy_without_dims():
    from aivp.visual.sheets import resolve_sheet_slots
    from aivp.visual.prompts import EXPRESSION_SLOTS

    slots = resolve_sheet_slots(group="expression", expression_dims=None)
    assert len(slots) == len(EXPRESSION_SLOTS)


def test_expression_slots_have_distinct_cues():
    """Each expression must carry unique mouth/eye/brow tokens for separation."""
    cues = {
        "expr_calm": ("neutral", "closed mouth"),
        "expr_smile": ("smile", "upturned"),
        "expr_happy": ("grin", "laugh"),
        "expr_confused": ("furrow", "tilt"),
        "expr_angry": ("frown", "glare"),
        "expr_sad": ("teary", "downturned"),
        "expr_surprised": ("wide eyes", "open mouth"),
        "expr_shy": ("blush", "avert"),
    }
    for key, _label, framing in EXPRESSION_SLOTS:
        low = framing.lower()
        assert key in cues, key
        assert any(token in low for token in cues[key]), (key, framing[:120])


def test_expression_prompt_drops_locked_smile_mouth():
    """Profile mouth cues like 抿唇带笑 must not fight angry/surprised prompts."""
    from aivp.visual.prompts import build_character_prompt, build_candidate_prompt
    from aivp.visual.profiles import normalize_look_fields

    profile = {
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，抿唇带笑，白发髻",
        "gender_presentation": "feminine",
        "age_look": "花甲前后老年面相",
        "appearance": {
            "face": "圆润多皱脸型，温和细眼，抿唇带笑",
            "face_shape": "圆润多皱脸型",
            "eyes": "温和细眼",
            "mouth": "抿唇带笑",
            "hair": "白发髻",
        },
        "wardrobe": {"default": "粗布家常衣衫"},
    }
    normalize_look_fields(profile)
    assert profile["default_expression"]
    assert "带笑" in profile["default_expression"] or "抿唇" in profile["default_expression"]
    assert "抿唇带笑" not in (profile.get("prompt_zh") or "")
    assert profile["appearance"]["mouth"] == "自然唇形"

    angry = build_character_prompt(
        "su_aivp",
        profile["prompt_zh"],
        EXPRESSION_SLOTS[4][2],  # angry framing
        gender_presentation="feminine",
        profile=profile,
        slot_key="expr_angry",
    )
    assert "抿唇带笑" not in angry
    assert profile["default_expression"] not in angry
    assert angry.lower().startswith("angry") or "angry furious" in angry.lower()
    assert "frown" in angry.lower() or "glare" in angry.lower()

    cand = build_candidate_prompt(profile, "front view, facing viewer")
    assert profile["default_expression"] in cand


def test_expression_prompts_are_face_only():
    from aivp.visual.prompts import build_character_prompt, sheet_negative_for

    for key, _label, framing in EXPRESSION_SLOTS:
        assert "facial close-up" in framing or "headshot" in framing
        assert "complete face" in framing or "forehead to chin" in framing
        assert "no body" in framing
        assert "full body" not in framing.lower()
        assert "face filling the frame" not in framing  # too-tight crop prior
        prompt = build_character_prompt(
            "lin_aivp", "青灰长衫少年", framing, gender_presentation="male"
        )
        assert "face" in prompt.lower() or "headshot" in prompt.lower()
        neg = sheet_negative_for("male", slot_key=key)
        assert "full body" in neg
        assert "half face" in neg or "cropped chin" in neg
        assert "close-up" not in neg  # must not reuse turnaround CHARACTER_NEGATIVE ban
        assert "upper body only" not in neg or "torso" in neg


def test_probe_framing_mentions_person():
    assert "1person" in PROBE_FRAMING
    assert "人物半身特写" in PROBE_FRAMING


def test_turnaround_prompts_force_solo_not_sheet_plate():
    from aivp.visual.prompts import build_character_prompt, sheet_negative_for

    for key, _label, framing in TURNAROUND_SLOTS:
        assert "solo" in framing
        assert "1person" in framing
        assert "turnaround sheet" not in framing.lower()
        assert "character sheet" not in framing.lower()
        prompt = build_character_prompt("lin_aivp", "青灰长衫少年", framing, gender_presentation="male")
        assert "1boy" in prompt or "male" in prompt
        assert "solo" in prompt
        neg = sheet_negative_for("male", slot_key=key)
        assert "multiple people" in neg or "2people" in neg
        assert "character sheet" in neg
        if key == "turnaround_back":
            assert "looking at viewer" in neg or "face" in neg
        if key == "turnaround_front":
            assert "back view" in neg
            assert "close-up" in neg  # turnaround still bans close-up


def test_candidate_prompt_locks_gender_and_wardrobe():
    from aivp.visual.prompts import build_candidate_prompt, candidate_negative_for, normalize_gender

    assert normalize_gender("unspecified", text_hints="青灰长衫少年") == "male"
    assert normalize_gender("unspecified", text_hints="绣裙少女") == "female"

    profile = {
        "trigger": "lin_aivp",
        "name": "林启之",
        "prompt_zh": "青灰长衫少年，黑发束冠",
        "gender_presentation": "masculine",
        "appearance": {"hair": "黑发束冠", "eyes": "深目"},
        "wardrobe": {"default": "青灰长衫"},
        "consistency_anchors": ["青灰长衫"],
    }
    prompt = build_candidate_prompt(profile, "solo, 1person, portrait")
    assert "1boy" in prompt
    assert "青灰长衫" in prompt
    assert "黑发束冠" in prompt
    assert "full body" in prompt
    assert "feet visible" in prompt
    assert "fully clothed" in prompt
    assert "blue-gray" in prompt or "long robe" in prompt
    neg = candidate_negative_for(profile)
    assert "1girl" in neg
    assert "different outfit" in neg or "costume change" in neg
    assert "shirtless" in neg or "bare chest" in neg
    assert "upper body only" in neg or "cropped feet" in neg


def test_candidate_prompt_middle_aged_male_outfit_english():
    from aivp.visual.prompts import build_candidate_prompt, candidate_negative_for, gender_lock_positive

    profile = {
        "trigger": "lin_yz_aivp",
        "name": "林砚之",
        "prompt_zh": "林砚之，男性，中年沉稳面相，身着深蓝行囊式披风短衫，国风动画角色定妆",
        "gender_presentation": "masculine",
        "age_look": "中年沉稳面相",
        "wardrobe": {"default": "深蓝行囊式披风短衫", "colors": ["深蓝"]},
    }
    assert "middle-aged" in gender_lock_positive(
        "male", age_look=profile["age_look"], text_hints=profile["prompt_zh"]
    )
    prompt = build_candidate_prompt(profile, "solo, 1person, full body")
    assert "middle-aged" in prompt
    assert "dark blue" in prompt
    assert "cloak" in prompt
    assert "short tunic" in prompt
    assert "fully clothed" in prompt
    assert "young man" not in prompt or "not young" in prompt
    neg = candidate_negative_for(profile)
    assert "shirtless" in neg
    assert "bare chest" in neg


def test_heiyiren_mask_and_black_outfit_lock():
    from aivp.visual.prompts import (
        age_band,
        build_candidate_prompt,
        candidate_negative_for,
        face_concealed,
        wardrobe_english_tokens,
    )

    profile = {
        "trigger": "heiyi_aivp",
        "name": "黑衣人",
        "prompt_zh": "黑衣人，男性，青壮年隐匿面相，身着紧身黑衣劲装，面巾或蒙面",
        "gender_presentation": "masculine",
        "age_look": "青壮年隐匿面相",
        "appearance": {
            "face": "瘦削长脸，冷峻细眼",
            "hair": "黑巾束发或罩面",
            "distinctive_marks": "面巾或蒙面",
            "body": "精干矫健",
        },
        "wardrobe": {"default": "紧身黑衣劲装", "colors": ["黑", "深灰"]},
        "consistency_anchors": ["紧身黑衣劲装", "黑巾束发或罩面", "黑衣人面部特征"],
    }
    assert age_band(profile["age_look"], name=profile["name"]) == "young_adult"
    assert face_concealed(profile) is True
    en = " ".join(
        wardrobe_english_tokens(
            profile["wardrobe"]["default"], colors=profile["wardrobe"]["colors"]
        )
    )
    assert "black" in en
    assert "no blue" in en
    prompt = build_candidate_prompt(profile, "full body")
    assert "masked" in prompt or "face covered" in prompt or "蒙面" in prompt
    assert "black" in prompt.lower()
    assert "瘦削长脸" not in prompt  # bare face detail suppressed
    assert "middle-aged" not in prompt
    assert "graying hair" not in prompt
    neg = candidate_negative_for(profile)
    assert "bare face" in neg or "exposed face" in neg
    assert "blue clothes" in neg or "teal" in neg


def test_age_lock_su_popo_and_chen_shouyi():
    from aivp.visual.prompts import (
        age_band,
        build_candidate_prompt,
        candidate_negative_for,
        gender_lock_positive,
    )

    su = {
        "trigger": "su_popo_aivp",
        "name": "苏婆婆",
        "prompt_zh": "苏婆婆，女性，花甲前后老年面相，白发，国风动画角色定妆",
        "gender_presentation": "feminine",
        "age_look": "花甲前后老年面相",
        "wardrobe": {"default": "素色布衣", "colors": ["灰"]},
    }
    assert age_band(su["age_look"], name=su["name"]) == "elder"
    su_pos = gender_lock_positive(
        "female", age_look=su["age_look"], text_hints=su["prompt_zh"], name=su["name"]
    )
    assert "elderly" in su_pos or "old woman" in su_pos or "grandmother" in su_pos
    assert "1girl" not in su_pos
    su_prompt = build_candidate_prompt(su, "solo, full body")
    assert "elderly" in su_prompt or "old woman" in su_prompt
    assert "white gray hair" in su_prompt or "gray white hair" in su_prompt
    su_neg = candidate_negative_for(su)
    assert "young girl" in su_neg or "1girl" in su_neg

    chen = {
        "trigger": "chen_sy_aivp",
        "name": "陈守义",
        "prompt_zh": "陈守义，男性，五十开外沧桑面相，花白发，国风动画角色定妆",
        "gender_presentation": "masculine",
        "age_look": "五十开外沧桑面相",
        "wardrobe": {"default": "青灰长衫", "colors": ["青灰"]},
    }
    assert age_band(chen["age_look"], name=chen["name"]) == "middle"
    chen_pos = gender_lock_positive(
        "male", age_look=chen["age_look"], text_hints=chen["prompt_zh"], name=chen["name"]
    )
    assert "middle-aged" in chen_pos or "fifties" in chen_pos or "weathered" in chen_pos
    assert "young adult man" not in chen_pos
    assert "1boy" not in chen_pos
    chen_prompt = build_candidate_prompt(chen, "solo, full body")
    assert "middle-aged" in chen_prompt or "weathered" in chen_prompt
    chen_neg = candidate_negative_for(chen)
    assert "young man" in chen_neg or "idol" in chen_neg


def test_turnaround_front_requires_full_body():
    front = next(s for s in TURNAROUND_SLOTS if s[0] == "turnaround_front")
    framing = front[2].lower()
    assert "full body" in framing
    assert "feet visible" in framing
    assert "head to toe" in framing
