from pathlib import Path
from aivp.models import Project, Job
from aivp.paths import ProjectPaths
from aivp.llm.fake import FakeLlm
from aivp.pipeline.runner import run_job
from aivp.config import Settings

SAMPLE = "第一章 开端\n\n李青云走进青云山。\n\n第二章 风云\n\n青云拔剑。\n"


def test_runner_full_pipeline_with_fake_llm(db_session, settings: Settings):
    proj = Project(id="p1", name="测书")
    db_session.add(proj)
    db_session.commit()
    paths = ProjectPaths(settings.data_root, "p1")
    paths.ensure()
    paths.source_txt.write_text(SAMPLE, encoding="utf-8")
    job = Job(id="j1", project_id="p1", status="queued")
    db_session.add(job)
    db_session.commit()
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山", "aliases": []}],
        "factions": [], "props": [],
        "events": [{"summary": "入山"}],
        "foreshadowing": [], "visual_cues": ["远山"], "voice_cues": [],
        "adaptation_notes": [],
    })
    run_job(db_session, settings, job_id="j1", llm=llm)
    db_session.refresh(job)
    assert job.status == "succeeded"
    assert paths.auto_bible_json.exists()
