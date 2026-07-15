#!/usr/bin/env python3
"""End-to-end short-novel pipeline verification (Fake LLM, no Ollama required)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

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
from aivp.schemas import REQUIRED_BIBLE_KEYS

SAMPLE = """第一章 雨夜破庙

林澈束起黑发，持旧刀沿血迹追至破庙门口。雨水顺着发梢落下，他贴着门缝听了一会儿，才推开腐朽木门。庙里神像半张脸陷在阴影中，空气潮湿阴冷。

第二章 庙中残响

林澈举刀走进正殿。地上一枚破碎玉佩反着微光，旁边有未干的墨迹家信。他俯身拾起玉佩，听见深处传来极轻的脚步声，眉心一紧。

第三章 夜路回城

林澈收好玉佩离开破庙，夜雨未歇。城门口巡夜捕快认出他，唤了一声「林捕快」。他未多言，只将玉佩收入怀中，迈步回城。
"""

EXTRACT = {
    "summary": "林澈雨夜追入破庙",
    "characters": [
        {"name": "林澈", "aliases": ["林捕快"], "evidence": "林澈束起黑发"},
    ],
    "locations": [
        {"name": "破庙", "aliases": ["荒庙"], "evidence": "追至破庙门口"},
    ],
    "factions": [],
    "props": [
        {"name": "旧刀", "aliases": [], "evidence": "持旧刀"},
        {"name": "玉佩", "aliases": [], "evidence": "破碎玉佩"},
    ],
    "events": [
        {
            "summary": "林澈追踪血迹进入破庙",
            "evidence": "沿血迹追至破庙门口",
        }
    ],
    "foreshadowing": [{"note": "未干家信", "evidence": "未干的墨迹家信"}],
    "relationships": [],
    "visual_cues": ["暴雨破庙门前"],
    "visual_candidates": [
        {
            "scene": "暴雨中林澈立于破庙门前",
            "evidence": "雨水顺着发梢落下",
            "visual_score": 0.9,
        }
    ],
    "voice_cues": ["压抑低语"],
    "adaptation_notes": ["少用正脸长对白"],
}


def main() -> int:
    tmp_path = Path(tempfile.mkdtemp(prefix="aivp-e2e-"))
    engine = None
    session = None
    try:
        db = tmp_path / "e2e.db"
        settings = Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{db.as_posix()}",
            chunk_size=4000,
            chunk_overlap=500,
            shot_force=True,
            _env_file=None,
        )
        engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        session.add(Project(id="e2e1", name="短样例破庙"))
        session.add(Job(id="je2e1", project_id="e2e1", status="queued"))
        session.commit()

        paths = ProjectPaths(tmp_path, "e2e1")
        paths.ensure()
        paths.source_txt.write_text(SAMPLE, encoding="utf-8")

        llm = FakeLlm(default=EXTRACT)
        run_job(session, settings, "je2e1", llm, shot_llm=None)
        session.refresh(session.get(Job, "je2e1"))
        job = session.get(Job, "je2e1")
        assert job is not None
        assert job.status == "succeeded", f"job failed: {job.status} {job.error_message}"

        checks = {
            "clean_metadata": paths.clean_metadata_json.exists(),
            "clean_report": paths.clean_report_json.exists(),
            "chapter_report": paths.chapter_report_json.exists(),
            "chunk_report": paths.chunk_report_json.exists(),
            "extract_report": paths.extract_report_json.exists(),
            "extract_errors": paths.extract_errors_json.exists(),
            "normalize_report": paths.normalize_report_json.exists(),
            "uncertain_entities": paths.uncertain_entities_json.exists(),
            "auto_bible": paths.auto_bible_json.exists(),
            "merged_bible": paths.merged_bible_json.exists(),
            "bible_meta": paths.bible_meta_json.exists(),
            "shot_script": paths.shot_script_json.exists(),
            "asset_plan": paths.asset_plan_json.exists(),
        }
        yamls = list(paths.shots_dir.rglob("*.yaml"))
        checks["shot_yamls"] = len(yamls) > 0

        chapters = json.loads(paths.chapters_json.read_text(encoding="utf-8"))
        chunks = [
            json.loads(line)
            for line in paths.chunks_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        bible = json.loads(paths.merged_bible_json.read_text(encoding="utf-8"))
        meta = json.loads(paths.bible_meta_json.read_text(encoding="utf-8"))
        shots_doc = json.loads(paths.shot_script_json.read_text(encoding="utf-8"))
        plan = json.loads(paths.asset_plan_json.read_text(encoding="utf-8"))

        assert len(chapters) >= 3, chapters
        assert chapters[0].get("start_offset") is not None
        assert chunks and chunks[0].get("chunk_id") and chunks[0].get("start_offset") is not None
        for k in REQUIRED_BIBLE_KEYS:
            assert k in bible, k
        assert bible.get("schema_version") == 3
        assert "blocks" in meta
        assert shots_doc.get("schema_version") == 2
        assert shots_doc.get("shot_count", 0) >= 1
        assert plan.get("characters") is not None

        failed = [k for k, ok in checks.items() if not ok]
        print("E2E short novel pipeline OK")
        print(f"  chapters={len(chapters)} chunks={len(chunks)} shots={shots_doc.get('shot_count')}")
        print(f"  yamls={len(yamls)} asset_chars={len(plan.get('characters') or [])}")
        print(f"  checks={json.dumps(checks, ensure_ascii=False)}")
        if failed:
            print(f"FAILED missing: {failed}")
            return 1
        return 0
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
        # Best-effort cleanup on Windows (sqlite file may linger briefly).
        try:
            import shutil

            shutil.rmtree(tmp_path, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
