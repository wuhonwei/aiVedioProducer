from pathlib import Path

from aivp.config import Settings
from aivp.visual.bootstrap import bootstrap_character
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.look_lock import look_lock_ref_path
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import read_profile_json


def test_bootstrap_character_reaches_awaiting_confirm(tmp_path: Path):
    settings = Settings(data_root=tmp_path, image_backend="stub")
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0003",
        "name": "苏婆婆",
        "tier": "major",
        "prompt_zh": "苏婆婆，女性，花甲，身着粗布家常衣衫",
        "gender_presentation": "feminine",
        "age_look": "花甲前后老年面相",
        "wardrobe": {"default": "粗布家常衣衫", "colors": ["米褐"]},
    }
    entity = {
        "id": "ent_0003",
        "name": "苏婆婆",
        "evidence": "白发苍苍的老婆婆，穿着粗布衣衫，眼神温和",
    }
    backend = StubImageBackend()
    # Smaller counts for speed via settings overrides
    settings.bootstrap_lock_candidate_count = 10
    settings.bootstrap_lock_batch_retries = 1
    settings.bootstrap_slot_retries = 1
    settings.bootstrap_archive_top_k = 2

    out = bootstrap_character(
        vpaths,
        character,
        backend,
        settings=settings,
        vision=None,  # heuristic pass
        llm=None,
        entity=entity,
    )
    assert out["status"] == "awaiting_confirm"
    assert out.get("look_lock_file")
    assert look_lock_ref_path(vpaths, "ent_0003")
    profile = read_profile_json(vpaths.profile_json("ent_0003"))
    assert profile is not None
    assert profile.get("bootstrap_status") == "awaiting_confirm"
    assert profile.get("train_status") == "awaiting_confirm"
    curated = list(vpaths.curated_dir("ent_0003").glob("*.png"))
    assert curated, "expected curated train images"
