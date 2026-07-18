import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.visual.location_profiles import ensure_location_profile, save_location_profile
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, save_profile


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{tmp_path / 't2i_shot.db'}",
            image_backend="stub",
        )
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    return TestClient(app)


@pytest.fixture
def project_id(client: TestClient, tmp_path: Path) -> str:
    pid = client.post("/api/projects", json={"name": "t2i-shot"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "id": "ent_1",
                        "name": "林砚之",
                        "tier": "major",
                        "prompt_zh": "青灰布衣少年",
                        "gender_presentation": "masculine",
                    }
                ],
                "locations": [
                    {
                        "id": "loc_1",
                        "name": "渡口",
                        "tier": "major",
                        "prompt_zh": "青石渡口",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pid


def _seed_loc_and_char(tmp_path: Path, project_id: str) -> None:
    v = VisualPaths(tmp_path, project_id)
    v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口"}
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")


def _seed_char(tmp_path: Path, project_id: str) -> None:
    v = VisualPaths(tmp_path, project_id)
    v.ensure()
    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    ensure_profile(v, ch)


@pytest.fixture
def seeded_loc_and_char(tmp_path: Path, project_id: str) -> str:
    _seed_loc_and_char(tmp_path, project_id)
    return project_id


@pytest.fixture
def seeded_char(tmp_path: Path, project_id: str) -> str:
    _seed_char(tmp_path, project_id)
    return project_id


def test_t2i_shot_defaults_location_lora_off(
    client: TestClient, project_id: str, seeded_loc_and_char: str
):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={
            "location_id": "loc_1",
            "character_ids": ["ent_1"],
            "prompt": "远望江雾",
            "shot_id": "s1",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["use_location_lora"] is False
    assert all(x["name"] != "dukou_loc.safetensors" for x in data.get("loras") or [])


def test_t2i_shot_can_enable_location_lora(
    client: TestClient, project_id: str, seeded_loc_and_char: str
):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={
            "location_id": "loc_1",
            "character_ids": ["ent_1"],
            "prompt": "远望江雾",
            "shot_id": "s1",
            "use_location_lora": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["use_location_lora"] is True
    assert data["loras"][0]["name"] == "dukou_loc.safetensors"


def test_t2i_probe_still_uses_character_path(
    client: TestClient, project_id: str, seeded_char: str
):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={"character_id": "ent_1", "prompt": "站立", "is_probe": True},
    )
    assert r.status_code == 200
    assert "file" in r.json() or "path" in r.json()
