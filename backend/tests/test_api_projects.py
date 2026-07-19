from pathlib import Path

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


def test_delete_project_removes_db_and_disk(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del.db'}")
    )
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "待删"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    (paths.root / "marker.txt").write_text("x", encoding="utf-8")
    assert paths.root.is_dir()

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["id"] == pid
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/projects").json())
    assert not paths.root.exists()


def test_delete_project_not_found(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del2.db'}")
    )
    client = TestClient(app)
    r = client.delete("/api/projects/missingproject")
    assert r.status_code == 404


def test_delete_project_invalid_id(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del3.db'}")
    )
    client = TestClient(app)
    for bad in ["../etc", "a/b", "a\\b", ""]:
        # empty path may 404/405 depending on routing; skip "" if router never matches
        if not bad:
            continue
        r = client.delete(f"/api/projects/{bad}")
        assert r.status_code in (400, 404, 422), (bad, r.status_code, r.text)


def test_delete_project_rejects_dotdot_id(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del3.db'}")
    )
    client = TestClient(app)
    r = client.delete("/api/projects/%2e%2e")  # ".."
    assert r.status_code == 400


def test_delete_project_disk_failure_still_removes_db(
    tmp_path: Path, monkeypatch
):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del_disk.db'}")
    )
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "磁盘失败"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    (paths.root / "marker.txt").write_text("x", encoding="utf-8")
    assert paths.root.is_dir()

    def fail_rmtree(_path):
        raise OSError("permission denied")

    monkeypatch.setattr("aivp.api.routes_projects.shutil.rmtree", fail_rmtree)

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["id"] == pid
    assert body["warning"].startswith("disk_delete_failed")
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/projects").json())
