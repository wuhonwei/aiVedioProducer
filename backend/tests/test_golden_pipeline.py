from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aivp.config import Settings
from aivp.db import Base
from aivp.llm.fake import FakeLlm
from aivp.models import Job, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.runner import run_job
from aivp.schemas import REQUIRED_BIBLE_KEYS


def test_golden_two_chapter_pipeline(tmp_path: Path):
    db = tmp_path / "g.db"
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{db}")
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Project(id="g1", name="金样"))
    session.add(Job(id="gj1", project_id="g1", status="queued"))
    session.commit()
    paths = ProjectPaths(tmp_path, "g1")
    paths.ensure()
    fixture = Path(__file__).parent / "fixtures" / "sample_chapter.txt"
    paths.source_txt.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山", "aliases": []}],
        "factions": [{"name": "天机阁", "aliases": []}],
        "props": [{"name": "饮虹", "aliases": []}],
        "events": [{"summary": "关键情节"}],
        "foreshadowing": [{"note": "剑意"}],
        "visual_cues": ["水墨山门"],
        "voice_cues": ["沉稳男声"],
        "adaptation_notes": ["夜宴戏加长"],
    })
    run_job(session, settings, "gj1", llm)
    import json

    bible = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
    for k in REQUIRED_BIBLE_KEYS:
        assert k in bible
    lead = next(c for c in bible["characters"] if c["name"] == "李青云")
    assert lead.get("prompt_zh")
    assert bible["character_visuals"][0].get("notes")
    assert bible["timeline"]
    assert any(e.get("visual_beat") for e in bible["timeline"])
