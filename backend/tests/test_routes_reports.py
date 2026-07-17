import json

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths


def _client(tmp_path):
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{tmp_path / 'reports.db'}",
    )
    app = create_app(settings)
    return TestClient(app), settings


def test_list_and_get_pipeline_reports(tmp_path):
    client, settings = _client(tmp_path)
    pid = client.post("/api/projects", json={"name": "Reports"}).json()["id"]
    paths = ProjectPaths(settings.data_root, pid)
    paths.ensure()

    listed = client.get(f"/api/projects/{pid}/reports")
    assert listed.status_code == 200
    names = {r["name"] for r in listed.json()["reports"]}
    assert {
        "clean",
        "metadata",
        "chapters",
        "chunks",
        "extract",
        "extract_errors",
        "normalize",
        "candidate_pairs",
        "uncertain_entities",
    }.issubset(names)
    assert all(r["available"] is False for r in listed.json()["reports"])

    missing = client.get(f"/api/projects/{pid}/reports/clean")
    assert missing.status_code == 404

    paths.clean_report_json.write_text(
        json.dumps({"removed_lines": 1}, ensure_ascii=False), encoding="utf-8"
    )
    paths.metadata_json.write_text(
        json.dumps({"detected_encoding": "utf-8"}, ensure_ascii=False), encoding="utf-8"
    )
    paths.chapter_report_json.write_text(
        json.dumps({"chapter_count": 2}, ensure_ascii=False), encoding="utf-8"
    )

    clean = client.get(f"/api/projects/{pid}/reports/clean")
    assert clean.status_code == 200
    assert clean.json()["removed_lines"] == 1

    meta = client.get(f"/api/projects/{pid}/reports/metadata")
    assert meta.status_code == 200
    assert meta.json()["detected_encoding"] == "utf-8"

    chapters = client.get(f"/api/projects/{pid}/reports/chapters")
    assert chapters.status_code == 200
    assert chapters.json()["chapter_count"] == 2

    listed2 = client.get(f"/api/projects/{pid}/reports")
    by_name = {r["name"]: r["available"] for r in listed2.json()["reports"]}
    assert by_name["clean"] is True
    assert by_name["metadata"] is True
    assert by_name["chapters"] is True
    assert by_name["chunks"] is False

    unknown = client.get(f"/api/projects/{pid}/reports/not_a_report")
    assert unknown.status_code == 404
