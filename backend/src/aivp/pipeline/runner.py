from sqlalchemy.orm import Session
from aivp.config import Settings
from aivp.models import Job, JobStep, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.types import STAGE_ORDER
from aivp.pipeline.clean import run_clean
from aivp.pipeline.chapters import run_chapter_split
from aivp.pipeline.chunks import run_chunk
from aivp.pipeline.extract import run_extract
from aivp.pipeline.normalize import run_normalize
from aivp.pipeline.timeline import run_timeline
from aivp.pipeline.arcs import run_arcs
from aivp.pipeline.assemble import run_assemble


def run_job(session: Session, settings: Settings, job_id: str, llm) -> None:
    job = session.get(Job, job_id)
    if not job:
        raise KeyError(job_id)
    project = session.get(Project, job.project_id)
    paths = ProjectPaths(settings.data_root, job.project_id)
    paths.ensure()
    start_idx = 0
    if job.resume_from_step and job.resume_from_step in STAGE_ORDER:
        start_idx = STAGE_ORDER.index(job.resume_from_step)
    job.status = "running"
    session.commit()
    warnings: list[str] = []
    try:
        for step in STAGE_ORDER[start_idx:]:
            job.current_step = step
            session.add(JobStep(job_id=job.id, step=step, status="running"))
            session.commit()
            if step == "01_clean":
                run_clean(paths.source_txt, paths.clean_txt)
            elif step == "02_chapters":
                run_chapter_split(paths.clean_txt, paths.chapters_json)
            elif step == "03_chunks":
                chunks = run_chunk(paths.chapters_json, paths.chunks_jsonl, settings.chunk_size, settings.chunk_overlap)
                job.chunks_total = len(chunks)
            elif step == "04_extract":
                result = run_extract(paths, llm, settings.extract_max_retries, settings.skip_bad_chunks)
                job.chunks_done = result["done"]
                warnings.extend(result.get("errors", []))
            elif step == "05_normalize":
                run_normalize(paths.extract_dir, paths.entities_json)
            elif step == "06_timeline":
                run_timeline(paths.chunks_jsonl, paths.extract_dir, paths.events_json)
            elif step == "07_arcs":
                run_arcs(paths.chapters_json, paths.events_json, paths.arcs_json)
            elif step == "08_bible":
                run_assemble(paths, project.name, warnings=warnings)
            session.add(JobStep(job_id=job.id, step=step, status="succeeded"))
            session.commit()
        job.status = "succeeded"
        job.error_message = None
        session.commit()
    except Exception as e:  # noqa: BLE001
        job.status = "step_failed"
        job.error_message = str(e)
        session.add(JobStep(job_id=job.id, step=job.current_step or "unknown", status="failed", detail=str(e)))
        session.commit()
        raise
