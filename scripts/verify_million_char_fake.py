#!/usr/bin/env python3
"""~120k-char fake novel e2e with Fake LLM (no Ollama)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Allow running from repo root or scripts/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aivp.config import Settings
from aivp.db import Base
from aivp.llm.fake import FakeLlm
from aivp.models import Job, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.runner import run_job


def _build_source(min_chars: int = 120_000) -> str:
    parts = []
    i = 1
    while sum(len(p) for p in parts) < min_chars:
        body = (
            f"李青云第{i}日于青云山炼气，遇见玄霜剑与天机阁弟子。"
            f"风过松林，鹤唳数声。青衣客言道：前路未歇，伏笔已埋。"
        ) * 40
        parts.append(f"第{i}章 青云行{i}\n\n{body}\n\n")
        i += 1
    return "".join(parts)


def main() -> int:
    source = _build_source()
    print(f"source_chars={len(source)} chapters≈{source.count(chr(31532))}")
    root = Path(tempfile.mkdtemp(prefix="aivp_million_"))
    engine = None
    session = None
    try:
        settings = Settings(
            data_root=root / "data",
            db_url=f"sqlite:///{(root / 'aivp.db').as_posix()}",
            extract_workers=4,
            volume_max_chars=40_000,
            volume_max_chapters=20,
            enrich_event_window=40,
            timeline_page_size=50,
            shot_require_deepseek=False,
        )
        settings.data_root.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        project = Project(id="million_fake", name="百万假文")
        session.add(project)
        job = Job(id="job1", project_id=project.id, status="queued")
        session.add(job)
        session.commit()

        paths = ProjectPaths(settings.data_root, project.id)
        paths.ensure()
        paths.source_txt.write_text(source, encoding="utf-8")

        llm = FakeLlm(
            default={
                "summary": "青云修炼",
                "characters": [{"name": "李青云", "aliases": [], "evidence": "李青云"}],
                "locations": [{"name": "青云山", "aliases": [], "evidence": "青云山"}],
                "factions": [{"name": "天机阁", "aliases": [], "evidence": "天机阁"}],
                "props": [{"name": "玄霜剑", "aliases": [], "evidence": "玄霜剑"}],
                "events": [{"summary": "李青云于青云山遇见天机阁弟子", "evidence": "遇见"}],
                "foreshadowing": [],
                "relationships": [],
                "visual_cues": ["松林鹤唳"],
                "visual_candidates": [],
                "voice_cues": [],
                "adaptation_notes": [],
                "logline": "少年入山，剑光破局。",
                "worldbuilding": {"summary": "山门林立", "rules": ["灵气稀缺"]},
                "character_relations": [],
                "plot_overview": "入山",
                "synopsis": "本卷青云山上修炼遇敌。",
                "key_turns": ["入山", "遇敌"],
                "shots": [],
                "majors": {},
            }
        )
        run_job(session, settings, job.id, llm, shot_llm=None)
        session.refresh(job)
        assert job.status == "succeeded", job.error_message

        assert paths.volumes_json.exists()
        volumes = json.loads(paths.volumes_json.read_text(encoding="utf-8"))
        assert volumes["volume_count"] >= 2
        assert paths.entities_json.exists()
        assert paths.events_json.exists()
        assert paths.timeline_index_json.exists()
        events = json.loads(paths.events_json.read_text(encoding="utf-8"))
        assert len(events) >= 1
        bible = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
        assert bible["timeline_ref"]["total_count"] == len(events)
        assert paths.volume_synopses_json.exists()
        synopses = json.loads(paths.volume_synopses_json.read_text(encoding="utf-8"))
        assert len(synopses) == volumes["volume_count"]
        assert paths.shot_script_json.exists()
        print(
            "ok",
            f"volumes={volumes['volume_count']}",
            f"events={len(events)}",
            f"synopses={len(synopses)}",
        )
        return 0
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
        try:
            import shutil

            shutil.rmtree(root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
