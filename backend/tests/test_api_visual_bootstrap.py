from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths


def _seed_bible(client: TestClient, tmp_path: Path) -> str:
    pid = client.post("/api/projects", json={"name": "bootstrap"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        __import__("json").dumps(
            {
                "characters": [
                    {
                        "id": "ent_0003",
                        "name": "苏婆婆",
                        "tier": "major",
                        "prompt_zh": "苏婆婆，女性，花甲，身着粗布家常衣衫",
                        "gender_presentation": "feminine",
                        "age_look": "花甲前后老年面相",
                        "wardrobe": {"default": "粗布家常衣衫", "colors": ["米褐"]},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths.entities_json.parent.mkdir(parents=True, exist_ok=True)
    paths.entities_json.write_text(
        __import__("json").dumps(
            {
                "characters": [
                    {
                        "id": "ent_0003",
                        "name": "苏婆婆",
                        "evidence": "白发苍苍的老婆婆，穿着粗布衣衫，眼神温和",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pid


def test_visual_bootstrap_job_confirm_and_swap(tmp_path: Path):
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{tmp_path / 'bs.db'}",
        image_backend="stub",
        bootstrap_lock_candidate_count=10,
        bootstrap_lock_batch_retries=1,
        bootstrap_slot_retries=1,
        bootstrap_archive_top_k=2,
    )
    app = create_app(settings)
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = _seed_bible(client, tmp_path)

    job = client.post(
        f"/api/projects/{pid}/visual/bootstrap",
        json={"character_ids": ["ent_0003"]},
    )
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    assert job.json()["kind"] == "visual_bootstrap"
    # Inline worker mutates the job file; re-fetch status.
    body = client.get(f"/api/projects/{pid}/visual/jobs/{jid}").json()
    assert body["status"] == "succeeded", body.get("error")
    assert body.get("result", {}).get("count") == 1
    assert body["result"]["characters"][0]["status"] == "awaiting_confirm"

    listed = client.get(f"/api/projects/{pid}/visual/characters").json()
    ch = listed["characters"][0]
    assert ch["bootstrap_status"] == "awaiting_confirm"
    assert ch["look_lock_ready"] is True
    archive = ch.get("look_lock_archive") or []
    assert archive, "expected archived lock alternatives"

    swap = client.post(
        f"/api/projects/{pid}/visual/characters/ent_0003/bootstrap/swap-look-lock",
        json={"filename": archive[0], "folder": "look_lock_archive"},
    )
    assert swap.status_code == 200, swap.text
    assert swap.json()["swapped_from"]["file"] == archive[0]

    confirm = client.post(
        f"/api/projects/{pid}/visual/characters/ent_0003/bootstrap/confirm"
    )
    assert confirm.status_code == 200
    assert confirm.json()["bootstrap_status"] == "confirmed"
    assert confirm.json()["train_status"] == "curated_ready"

    listed2 = client.get(f"/api/projects/{pid}/visual/characters").json()
    assert listed2["characters"][0]["bootstrap_status"] == "confirmed"
    assert listed2["characters"][0]["train_status"] == "curated_ready"
