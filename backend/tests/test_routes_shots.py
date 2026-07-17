import json

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths
from aivp.pipeline.shot_upgrade import upgrade_shot_to_v2, write_shot_script_index


def _client(tmp_path):
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{tmp_path / 'shots.db'}",
    )
    app = create_app(settings)
    return TestClient(app), settings


def _seed_shots(paths: ProjectPaths):
    shots = [
        upgrade_shot_to_v2(
            {
                "order": 1,
                "action": "推门",
                "cast": ["林澈"],
                "location_name": "破庙",
                "chapter_id": "chapter_0001",
                "event_id": "event_0001",
                "chunk_id": "chapter_0001_chunk_0001",
            },
            1,
        ),
        upgrade_shot_to_v2(
            {
                "order": 2,
                "action": "拔刀",
                "cast": ["林澈"],
                "location_name": "破庙",
                "chapter_id": "chapter_0001",
                "event_id": "event_0002",
            },
            2,
        ),
    ]
    doc = {
        "schema_version": 2,
        "event_count": 2,
        "shot_count": 2,
        "shots": shots,
        "warnings": [],
        "volumes": [],
    }
    paths.ensure()
    paths.shot_script_dir.mkdir(parents=True, exist_ok=True)
    paths.shot_script_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_shot_script_index(paths.shot_script_index_json, doc)
    return shots


def test_shots_filter_review_lock_and_asset_plan(tmp_path):
    client, settings = _client(tmp_path)
    pid = client.post("/api/projects", json={"name": "Shots"}).json()["id"]
    paths = ProjectPaths(settings.data_root, pid)
    shots = _seed_shots(paths)
    shot_id = shots[0]["shot_id"]

    listed = client.get(f"/api/projects/{pid}/shots?offset=0&limit=10")
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 2

    reviewed = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/review",
        json={"status": "approved"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "approved"
    assert paths.asset_plan_json.exists()
    plan = json.loads(paths.asset_plan_json.read_text(encoding="utf-8"))
    assert plan["generated_from"]["shot_review_status"] == "approved_only"
    assert plan["characters"]

    filtered = client.get(f"/api/projects/{pid}/shots?review_status=approved&offset=0&limit=10")
    assert filtered.json()["total_count"] == 1

    locked = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/review",
        json={"status": "locked"},
    )
    assert locked.json()["locked"] is True
    blocked = client.patch(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"visual_prompt": "改"},
    )
    assert blocked.status_code == 409

    unlocked = client.patch(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"review_status": "needs_review", "visual_prompt": "新提示"},
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["locked"] is False

    exported = client.post(f"/api/projects/{pid}/shots/export-yaml?approved_only=false")
    assert exported.status_code == 200

    regen = client.post(f"/api/projects/{pid}/assets/plan/regenerate")
    assert regen.status_code == 200
    assert "characters" in regen.json()

    # Approve again then patch asset status
    client.post(f"/api/projects/{pid}/shots/{shot_id}/review", json={"status": "approved"})
    plan2 = client.get(f"/api/projects/{pid}/assets/plan").json()
    cid = plan2["characters"][0]["id"]
    patched = client.patch(
        f"/api/projects/{pid}/assets/plan/characters/{cid}",
        json={"status": "approved", "priority": "high"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "approved"

    bad = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/review",
        json={"status": "nope"},
    )
    assert bad.status_code == 400

    assert paths.shot_script_index_json.exists()
