from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.visual.candidates import generate_candidates_for_character
from aivp.visual.image_backend import StubImageBackend, build_sdxl_img2img_workflow
from aivp.visual.look_lock import resolve_look_lock, set_look_lock
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile


def test_img2img_workflow_uses_load_image_and_denoise():
    wf = build_sdxl_img2img_workflow(
        checkpoint="Guofeng4.2XL.safetensors",
        prompt="1boy, lin_aivp",
        negative="1girl",
        seed=7,
        input_image="ref.png",
        denoise=0.48,
    )
    assert wf["11"]["class_type"] == "AIVPLoadImage"
    assert wf["11"]["inputs"]["image"] == "ref.png"
    assert wf["13"]["class_type"] == "VAEEncode"
    assert wf["3"]["inputs"]["denoise"] == 0.48
    assert wf["3"]["inputs"]["latent_image"] == ["13", 0]


def test_set_look_lock_and_candidates_use_ref(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林启之",
        "tier": "major",
        "prompt_zh": "青灰长衫少年",
        "gender_presentation": "masculine",
        "wardrobe": {"default": "青灰长衫"},
    }
    ensure_profile(vpaths, character)
    backend = StubImageBackend()
    first = generate_candidates_for_character(vpaths, character, backend, count=1)
    src = first["files"][0]
    locked = set_look_lock(vpaths, "ent_0001", folder="candidates", filename=src, denoise=0.5)
    assert locked["look_lock"]["file"] == src
    ref, denoise = resolve_look_lock(vpaths, "ent_0001")
    assert ref and ref.exists()
    assert denoise == 0.5

    again = generate_candidates_for_character(vpaths, character, backend, count=2)
    assert again["look_lock"] is True
    assert 0.60 <= float(again["denoise"]) <= 0.78
    meta = (vpaths.candidates_dir("ent_0001") / again["files"][0]).with_suffix(".json")
    payload = __import__("json").loads(meta.read_text(encoding="utf-8"))
    assert payload.get("ref_image")
    assert float(payload.get("denoise") or 0) >= 0.60

    from aivp.visual.sheets import generate_character_sheets

    sheets = generate_character_sheets(
        vpaths, character, backend, slot_keys=["turnaround_front", "expr_calm", "turnaround_side"]
    )
    assert sheets["look_lock"] is True
    front_meta = (
        vpaths.sheets_dir("ent_0001") / sheets["files"][0]["file"]
    ).with_suffix(".meta.json")
    front_payload = __import__("json").loads(front_meta.read_text(encoding="utf-8"))
    assert front_payload.get("look_lock") is True
    assert float(front_payload.get("denoise") or 0) >= 0.45

    expr = next(f for f in sheets["files"] if f["key"] == "expr_calm")
    expr_meta = (vpaths.sheets_dir("ent_0001") / expr["file"]).with_suffix(".meta.json")
    expr_payload = __import__("json").loads(expr_meta.read_text(encoding="utf-8"))
    assert expr_payload.get("look_lock_ref_kind") == "face"
    face_ref = vpaths.character_dir("ent_0001") / "look_lock" / "face_ref.png"
    assert face_ref.exists()

    side = next(f for f in sheets["files"] if f["key"] == "turnaround_side")
    side_meta = (vpaths.sheets_dir("ent_0001") / side["file"]).with_suffix(".meta.json")
    side_payload = __import__("json").loads(side_meta.read_text(encoding="utf-8"))
    assert side_payload.get("look_lock") is True
    assert float(side_payload.get("denoise") or 0) >= 0.88
    assert float(side_payload.get("cfg") or 0) >= 9.0


def test_face_crop_from_look_lock(tmp_path: Path):
    from PIL import Image

    from aivp.visual.look_lock import ensure_face_ref, set_look_lock

    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林启之",
        "tier": "major",
        "prompt_zh": "青灰长衫少年",
    }
    ensure_profile(vpaths, character)
    cand_dir = vpaths.candidates_dir("ent_0001")
    cand_dir.mkdir(parents=True, exist_ok=True)
    src = cand_dir / "full.png"
    Image.new("RGB", (384, 768), color=(40, 80, 120)).save(src)
    set_look_lock(vpaths, "ent_0001", folder="candidates", filename="full.png", denoise=0.55)
    face = ensure_face_ref(vpaths, "ent_0001")
    assert face.exists()
    im = Image.open(face)
    assert im.size == (768, 768)
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'ll.db'}", image_backend="stub")
    )
    app.state.run_jobs_inline = True
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "定妆"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    paths.auto_bible_json.write_text(
        __import__("json").dumps(
            {
                "characters": [
                    {
                        "id": "ent_0001",
                        "name": "林启之",
                        "tier": "major",
                        "prompt_zh": "青灰长衫少年",
                        "gender_presentation": "masculine",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    job = client.post(
        f"/api/projects/{pid}/visual/candidates",
        json={"character_ids": ["ent_0001"], "count": 1},
    )
    assert job.status_code == 202
    listed = client.get(f"/api/projects/{pid}/visual/characters").json()
    fname = listed["characters"][0]["candidates"][0]
    put = client.put(
        f"/api/projects/{pid}/visual/characters/ent_0001/look-lock",
        json={"folder": "candidates", "filename": fname, "denoise": 0.45},
    )
    assert put.status_code == 200
    assert put.json()["look_lock"]["file"] == fname
    listed2 = client.get(f"/api/projects/{pid}/visual/characters").json()
    assert listed2["characters"][0]["look_lock_ready"] is True
    ref = client.get(
        f"/api/projects/{pid}/visual/characters/ent_0001/files/look_lock/ref.png"
    )
    assert ref.status_code == 200
    cleared = client.delete(f"/api/projects/{pid}/visual/characters/ent_0001/look-lock")
    assert cleared.status_code == 200
    assert cleared.json()["look_lock"] is None
