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
    neg = candidate_negative_for(profile)
    assert "1girl" in neg
    assert "different outfit" in neg or "costume change" in neg
