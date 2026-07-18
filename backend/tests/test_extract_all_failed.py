from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aivp.config import Settings
from aivp.db import Base
from aivp.llm.fake import FakeLlm
from aivp.models import Job, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.runner import run_job


class _BoomLlm(FakeLlm):
    def complete_json(self, system, user, *, should_cancel=None):  # noqa: ANN001
        raise ConnectionRefusedError(10061, "connection refused")


def test_run_job_fails_when_all_extract_chunks_fail(tmp_path: Path):
    db = tmp_path / "e.db"
    settings = Settings(
        data_root=tmp_path,
        db_url=f"sqlite:///{db}",
        skip_bad_chunks=True,
        extract_max_retries=1,
    )
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Project(id="e1", name="空抽"))
    session.add(Job(id="ej1", project_id="e1", status="queued"))
    session.commit()
    paths = ProjectPaths(tmp_path, "e1")
    paths.ensure()
    fixture = Path(__file__).parent / "fixtures" / "sample_chapter.txt"
    paths.source_txt.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(RuntimeError, match="extract_all_chunks_failed"):
        run_job(session, settings, "ej1", _BoomLlm())

    job = session.get(Job, "ej1")
    assert job is not None
    assert job.status == "step_failed"
    assert "extract_all_chunks_failed" in (job.error_message or "")
    assert job.current_step == "04_extract"
