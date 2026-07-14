from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths


def test_create_and_list_projects(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}"))
    client = TestClient(app)
    r = client.post("/api/projects", json={"name": "\u4ed9\u4fa0\u6d4b"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert isinstance(pid, str) and len(pid) >= 8
    content = "\u7b2c\u4e00\u7ae0\n\n\u4f60\u597d".encode("utf-8")
    files = {"file": ("book.txt", content, "text/plain")}
    up = client.post(f"/api/projects/{pid}/source", files=files)
    assert up.status_code == 200
    assert client.get("/api/projects").json()[0]["name"] == "\u4ed9\u4fa0\u6d4b"
    paths = ProjectPaths(tmp_path, pid)
    assert paths.source_txt.read_text(encoding="utf-8") == "\u7b2c\u4e00\u7ae0\n\n\u4f60\u597d"


def test_get_project_not_found(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}"))
    client = TestClient(app)
    r = client.get("/api/projects/missing")
    assert r.status_code == 404
    body = r.json()
    assert body["code"]
    assert body["message"]
