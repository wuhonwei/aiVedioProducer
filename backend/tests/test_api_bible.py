import json
from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths


def test_bible_patch_and_get_merged(tmp_path):
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}")
    app = create_app(settings)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    auto = {"logline": "\u81ea\u52a8", "characters": [], "project_meta": {"title": "X"}}
    for k in ["worldbuilding","plot_structure","character_relations","locations","factions","props",
              "timeline","foreshadowing","adaptation_notes","visual_style","character_visuals",
              "voice_bible","production_constraints"]:
        auto.setdefault(k, [])
    paths.auto_bible_json.write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
    client.patch(f"/api/projects/{pid}/bible", json={"logline": "\u4eba\u5de5"})
    body = client.get(f"/api/projects/{pid}/bible").json()
    assert body["logline"] == "\u4eba\u5de5"


def test_bible_export_increments_version(tmp_path):
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}")
    app = create_app(settings)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    auto = {"logline": "\u81ea\u52a8", "characters": [], "project_meta": {"title": "X"}, "warnings": []}
    for k in ["worldbuilding","plot_structure","character_relations","locations","factions","props",
              "timeline","foreshadowing","adaptation_notes","visual_style","character_visuals",
              "voice_bible","production_constraints"]:
        auto.setdefault(k, [])
    paths.auto_bible_json.write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
    r = client.post(f"/api/projects/{pid}/exports")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["json_url"] == f"/api/projects/{pid}/exports/1/json"
    assert body["md_url"] == f"/api/projects/{pid}/exports/1/md"
    assert (paths.exports_dir / "story_bible.v001.json").exists()
    r2 = client.post(f"/api/projects/{pid}/exports")
    assert r2.json()["version"] == 2


def test_export_json_download_returns_200(tmp_path):
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}")
    app = create_app(settings)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    auto = {"logline": "\u81ea\u52a8", "characters": [], "project_meta": {"title": "X"}, "warnings": []}
    for k in ["worldbuilding","plot_structure","character_relations","locations","factions","props",
              "timeline","foreshadowing","adaptation_notes","visual_style","character_visuals",
              "voice_bible","production_constraints"]:
        auto.setdefault(k, [])
    paths.auto_bible_json.write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
    created = client.post(f"/api/projects/{pid}/exports").json()
    r = client.get(created["json_url"])
    assert r.status_code == 200
    assert r.json()["logline"] == "\u81ea\u52a8"
