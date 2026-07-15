import json

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths


def test_timeline_and_shots_pagination(tmp_path):
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{tmp_path / 'a.db'}",
        api_page_size=50,
    )
    app = create_app(settings)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "Paginate"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()

    events = [
        {"id": f"evt{i:04d}", "chapter_id": "ch001", "summary": f"事件{i}"}
        for i in range(1, 81)
    ]
    paths.events_json.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    r = client.get(f"/api/projects/{pid}/timeline?offset=0&limit=50")
    assert r.status_code == 200
    body = r.json()
    assert body["total_count"] == 80
    assert len(body["items"]) == 50
    assert body["has_more"] is True
    r2 = client.get(f"/api/projects/{pid}/timeline?offset=50&limit=50")
    assert len(r2.json()["items"]) == 30
    assert r2.json()["has_more"] is False

    shots = [
        {
            "shot_id": f"sh_evt{i:04d}_01",
            "event_id": f"evt{i:04d}",
            "order": 1,
            "action": f"a{i}",
            "visual_prompt": f"v{i}",
        }
        for i in range(1, 61)
    ]
    paths.shot_script_json.write_text(
        json.dumps(
            {"schema_version": 2, "shots": shots, "shot_count": len(shots)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    s = client.get(f"/api/projects/{pid}/shots?offset=0&limit=50")
    assert s.status_code == 200
    sb = s.json()
    assert sb["total_count"] == 60
    assert len(sb["items"]) == 50
    assert sb["has_more"] is True
    filtered = client.get(f"/api/projects/{pid}/shots?event_id=evt0001&limit=10")
    assert filtered.json()["total_count"] == 1
