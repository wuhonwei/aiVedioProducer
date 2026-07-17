from collections.abc import Callable
import json

from sqlalchemy.orm import Session

from aivp.config import Settings
from aivp.jobs.control import JobCancelled
from aivp.models import Job, JobStep, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.arcs import run_arcs
from aivp.pipeline.assemble import run_assemble
from aivp.pipeline.chapters import run_chapter_split
from aivp.pipeline.chunks import chunk_chapters, chunk_report, run_chunk
from aivp.pipeline.clean import run_clean
from aivp.pipeline.enrich import run_enrich
from aivp.pipeline.extract import run_extract
from aivp.pipeline.normalize import merge_volume_entities, run_normalize, run_normalize_volume
from aivp.pipeline.shot_script import run_shot_script
from aivp.pipeline.timeline import run_timeline
from aivp.pipeline.types import STAGE_ALIASES, STAGE_ORDER
from aivp.pipeline.volumes import (
    filter_chapters_by_range,
    filter_chapters_by_volume,
    run_plan_volumes,
)


def _load_volumes(paths: ProjectPaths) -> list[dict]:
    if not paths.volumes_json.exists():
        return []
    payload = json.loads(paths.volumes_json.read_text(encoding="utf-8"))
    return list(payload.get("volumes") or [])


def _resolve_chapters(
    paths: ProjectPaths,
    *,
    volume_id: str | None = None,
    chapter_from: str | None = None,
    chapter_to: str | None = None,
) -> list[dict]:
    chapters = json.loads(paths.chapters_json.read_text(encoding="utf-8"))
    if volume_id:
        volumes = _load_volumes(paths)
        vol = next((v for v in volumes if v.get("id") == volume_id), None)
        if vol is None:
            raise ValueError(f"volume_not_found:{volume_id}")
        return filter_chapters_by_volume(chapters, vol)
    return filter_chapters_by_range(
        chapters, chapter_from=chapter_from, chapter_to=chapter_to
    )


def run_job(
    session: Session,
    settings: Settings,
    job_id: str,
    llm,
    *,
    should_cancel: Callable[[], bool] | None = None,
    force_enrich: bool = False,
    force_shots: bool = False,
    shot_llm=None,
    volume_id: str | None = None,
    chapter_from: str | None = None,
    chapter_to: str | None = None,
) -> None:
    job = session.get(Job, job_id)
    if not job:
        raise KeyError(job_id)
    project = session.get(Project, job.project_id)
    if not project:
        raise KeyError(job.project_id)
    paths = ProjectPaths(settings.data_root, job.project_id)
    paths.ensure()
    start_idx = 0
    resume = job.resume_from_step
    if resume:
        resume = STAGE_ALIASES.get(resume, resume)
        if resume in STAGE_ORDER:
            start_idx = STAGE_ORDER.index(resume)
    job.status = "running"
    session.commit()
    warnings: list[str] = []
    range_active = bool(volume_id or chapter_from or chapter_to)

    def _check_cancel() -> None:
        if should_cancel and should_cancel():
            raise JobCancelled(job_id)

    try:
        for step in STAGE_ORDER[start_idx:]:
            _check_cancel()
            job.current_step = step
            session.add(JobStep(job_id=job.id, step=step, status="running"))
            session.commit()
            if step == "01_clean":
                run_clean(
                    paths.source_txt,
                    paths.clean_txt,
                    metadata_json=paths.metadata_json,
                    clean_report_json=paths.clean_report_json,
                )
            elif step == "02_chapters":
                run_chapter_split(
                    paths.clean_txt,
                    paths.chapters_json,
                    report_json=paths.chapter_report_json,
                )
                volumes = run_plan_volumes(
                    paths.chapters_json,
                    paths.volumes_json,
                    max_chars=settings.volume_max_chars,
                    max_chapters=settings.volume_max_chapters,
                )
                job.volumes_total = len(volumes)
                job.volumes_done = 0
                session.commit()
            elif step == "03_chunks":
                if not paths.volumes_json.exists() and paths.chapters_json.exists():
                    volumes = run_plan_volumes(
                        paths.chapters_json,
                        paths.volumes_json,
                        max_chars=settings.volume_max_chars,
                        max_chapters=settings.volume_max_chapters,
                    )
                    job.volumes_total = len(volumes)
                    session.commit()
                if range_active:
                    chapters = _resolve_chapters(
                        paths,
                        volume_id=volume_id,
                        chapter_from=chapter_from,
                        chapter_to=chapter_to,
                    )
                    chunks = chunk_chapters(
                        chapters, size=settings.chunk_size, overlap=settings.chunk_overlap
                    )
                    paths.chunks_jsonl.parent.mkdir(parents=True, exist_ok=True)
                    with paths.chunks_jsonl.open("w", encoding="utf-8") as f:
                        for c in chunks:
                            f.write(json.dumps(c, ensure_ascii=False) + "\n")
                    paths.chunk_report_json.write_text(
                        json.dumps(
                            chunk_report(chunks, settings.chunk_size, settings.chunk_overlap),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                else:
                    chunks = run_chunk(
                        paths.chapters_json,
                        paths.chunks_jsonl,
                        settings.chunk_size,
                        settings.chunk_overlap,
                        report_json=paths.chunk_report_json,
                    )
                job.chunks_total = len(chunks)
                job.chunks_done = 0
                session.commit()
            elif step == "04_extract":
                if job.chunks_total <= 0 and paths.chunks_jsonl.exists():
                    job.chunks_total = sum(
                        1
                        for line in paths.chunks_jsonl.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    )
                    session.commit()

                def _on_extract_progress(done: int, total: int) -> None:
                    job.chunks_done = done
                    job.chunks_total = total
                    session.commit()

                result = run_extract(
                    paths,
                    llm,
                    settings.extract_max_retries,
                    settings.skip_bad_chunks,
                    should_cancel=should_cancel,
                    on_progress=_on_extract_progress,
                    workers=settings.extract_workers,
                    progress_every=settings.extract_progress_every,
                    report_json=paths.extract_report_json,
                    errors_json=paths.extract_errors_json,
                )
                job.chunks_done = result["done"]
                job.chunks_total = result["total"]
                warnings.extend(result.get("errors", []))
                session.commit()
            elif step == "05_normalize":
                volumes = _load_volumes(paths)
                if volume_id:
                    volumes = [v for v in volumes if v.get("id") == volume_id]
                if volumes:
                    job.volumes_total = len(volumes)
                    job.volumes_done = 0
                    session.commit()
                    volume_maps: list[dict] = []
                    uncertain_all: list[dict] = []
                    for i, vol in enumerate(volumes, start=1):
                        _check_cancel()
                        out = paths.volume_entities_json(vol["id"])
                        run_normalize_volume(
                            paths.extract_dir,
                            out,
                            list(vol.get("chapter_ids") or []),
                        )
                        volume_maps.append(
                            json.loads(out.read_text(encoding="utf-8"))
                        )
                        unc_path = paths.volume_uncertain_json(vol["id"])
                        if unc_path.exists():
                            uncertain_all.extend(
                                json.loads(unc_path.read_text(encoding="utf-8"))
                            )
                        job.volumes_done = i
                        session.commit()
                    merged = merge_volume_entities(volume_maps)
                    entities = merged["entities"]
                    paths.entities_json.parent.mkdir(parents=True, exist_ok=True)
                    paths.entities_json.write_text(
                        json.dumps(entities, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    paths.uncertain_entities_json.write_text(
                        json.dumps(
                            merged.get("uncertain_entities") or uncertain_all,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    paths.candidate_pairs_json.write_text(
                        json.dumps(
                            merged.get("candidate_pairs")
                            or merged.get("uncertain_entities")
                            or [],
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    report = {
                        "entity_counts": {k: len(v) for k, v in entities.items()},
                        "uncertain_count": len(merged.get("uncertain_entities") or []),
                        "volume_count": len(volumes),
                        "auto_merged": True,
                    }
                    paths.normalize_report_json.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                else:
                    run_normalize(paths.extract_dir, paths.entities_json)
            elif step == "06_enrich_assets":

                def _on_enrich_progress(done: int, total: int) -> None:
                    job.chunks_done = done
                    job.chunks_total = total
                    session.commit()

                result = run_enrich(
                    paths,
                    settings,
                    llm,
                    should_cancel=should_cancel,
                    on_progress=_on_enrich_progress,
                    force=bool(force_enrich or settings.enrich_force),
                )
                warnings.extend(result.get("warnings") or [])
                session.commit()
            elif step == "07_timeline":
                run_timeline(
                    paths.chunks_jsonl,
                    paths.extract_dir,
                    paths.events_json,
                    enriched_json=paths.events_enriched_json,
                    page_size=settings.timeline_page_size,
                    pages_dir=paths.timeline_pages_dir,
                    index_json=paths.timeline_index_json,
                )
            elif step == "08_arcs":
                run_arcs(
                    paths.chapters_json,
                    paths.events_json,
                    paths.arcs_json,
                    extract_dir=paths.extract_dir,
                )
            elif step == "09_bible":
                run_assemble(
                    paths,
                    project.name,
                    warnings=warnings,
                    llm=llm,
                    should_cancel=should_cancel,
                    timeline_page_size=settings.timeline_page_size,
                )
            elif step == "10_shot_script":

                def _on_shot_progress(done: int, total: int) -> None:
                    job.chunks_done = done
                    job.chunks_total = total
                    session.commit()

                active_shot_llm = shot_llm
                if active_shot_llm is None and settings.shot_require_deepseek:
                    raise RuntimeError("deepseek_api_key_missing")
                result = run_shot_script(
                    paths,
                    settings,
                    active_shot_llm,
                    should_cancel=should_cancel,
                    on_progress=_on_shot_progress,
                    force=bool(force_shots or settings.shot_force),
                    volume_id=volume_id,
                    chapter_from=chapter_from,
                    chapter_to=chapter_to,
                )
                warnings.extend(result.get("warnings") or [])
                if result.get("skipped"):
                    warnings.append("shot_script_skipped_existing")
                session.commit()
            _check_cancel()
            session.add(JobStep(job_id=job.id, step=step, status="succeeded"))
            session.commit()
        job.status = "succeeded"
        job.error_message = None
        session.commit()
    except JobCancelled:
        job.status = "cancelled"
        job.error_message = "cancelled_by_user"
        session.add(
            JobStep(
                job_id=job.id,
                step=job.current_step or "unknown",
                status="cancelled",
                detail="cancelled_by_user",
            )
        )
        session.commit()
    except Exception as e:  # noqa: BLE001
        job.status = "step_failed"
        job.error_message = str(e)
        session.add(
            JobStep(
                job_id=job.id,
                step=job.current_step or "unknown",
                status="failed",
                detail=str(e),
            )
        )
        session.commit()
        raise
