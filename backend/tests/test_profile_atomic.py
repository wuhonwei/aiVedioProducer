import os
from pathlib import Path

from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import (
    atomic_write_json,
    ensure_profile,
    read_profile_json,
)


def test_read_profile_json_tolerates_empty_and_corrupt(tmp_path: Path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert read_profile_json(empty) is None

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert read_profile_json(bad) is None

    ok = tmp_path / "ok.json"
    atomic_write_json(ok, {"character_id": "ent_0001", "name": "林砚之"})
    loaded = read_profile_json(ok)
    assert loaded and loaded["name"] == "林砚之"


def test_ensure_profile_recovers_from_corrupt_file(tmp_path: Path):
    vpaths = VisualPaths(tmp_path, "p1")
    vpaths.ensure()
    character = {
        "id": "ent_0001",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "深蓝披风",
        "gender_presentation": "masculine",
        "wardrobe": {"default": "深蓝披风"},
    }
    path = vpaths.profile_json("ent_0001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")  # simulate mid-write race

    profile = ensure_profile(vpaths, character)
    assert profile["character_id"] == "ent_0001"
    assert profile["name"] == "林砚之"
    assert read_profile_json(path) is not None


def test_atomic_write_json_retries_winerror32(tmp_path: Path, monkeypatch):
    path = tmp_path / "p.json"
    calls = {"n": 0}

    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            err = OSError(13, "Permission denied")
            err.winerror = 32  # type: ignore[attr-defined]
            raise err
        return real_replace(src, dst)

    from aivp.visual import profiles as profiles_mod

    monkeypatch.setattr(profiles_mod.os, "replace", flaky_replace)
    atomic_write_json(path, {"ok": True})
    assert path.exists()
    assert calls["n"] == 3
