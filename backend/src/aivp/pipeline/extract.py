from __future__ import annotations

import json
from collections.abc import Callable

from aivp.jobs.control import JobCancelled
from aivp.llm.base import LlmClient
from aivp.paths import ProjectPaths
from aivp.pipeline.coerce_extract import coerce_extract
from aivp.schemas import ChunkExtract

SYSTEM = (
    "你是国风长篇结构化抽取器。只输出 JSON 对象，不要 markdown。"
    "键必须齐全: summary, characters, locations, factions, props, events, "
    "foreshadowing, relationships, visual_cues, visual_candidates, voice_cues, adaptation_notes。"
    "不得编造原文未出现的信息；缺信息用空数组或空字符串。"
    "characters/locations/factions/props 为对象数组，每项含 name、aliases[]、evidence(原文摘录)。"
    "events 为对象数组，每项至少含 summary 与 evidence。"
    "foreshadowing 为对象数组，每项至少含 note 与 evidence。"
    "visual_candidates 为对象数组，含 scene、evidence、visual_score。"
    "visual_cues/voice_cues/adaptation_notes 为 string 数组。"
)

EXAMPLE = (
    '{"summary":"林砚之抵达青川渡",'
    '"characters":[{"name":"林砚之","aliases":["少年"],"evidence":"林砚之立于渡口"}],'
    '"locations":[{"name":"青川渡","aliases":[],"evidence":"青川渡晨雾"}],'
    '"factions":[],"props":[{"name":"玉佩","aliases":[],"evidence":"腰间玉佩"}],'
    '"events":[{"summary":"林砚之抵达青川渡寻找陈守义","evidence":"他询问陈守义下落"}],'
    '"foreshadowing":[{"note":"未写完的家信","evidence":"家信墨迹未干"}],'
    '"relationships":[],'
    '"visual_cues":["江雾笼罩的青石渡口"],'
    '"visual_candidates":[{"scene":"江雾中的青石渡口","evidence":"江雾笼罩","visual_score":0.9}],'
    '"voice_cues":["低沉船夫嗓音"],'
    '"adaptation_notes":["开场用长镜头建立氛围"]}'
)


def extract_chunk(
    chunk: dict,
    llm: LlmClient,
    max_retries: int = 2,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    user = (
        f"章节:{chunk.get('chapter_title','')}\n"
        f"正文:\n{chunk['text']}\n"
        "请按 schema 抽取上述字段。关键事实必须附 evidence（原文短摘录）。示例形状:\n"
        f"{EXAMPLE}"
    )
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        if should_cancel and should_cancel():
            raise JobCancelled(chunk["id"])
        try:
            raw = llm.complete_json(
                SYSTEM,
                user if attempt == 0 else user + "\n请严格修复为合法 JSON schema，并为事实补充 evidence。",
                should_cancel=should_cancel,
            )
            coerced = coerce_extract(raw)
            if attempt > 0:
                coerced["quality"]["json_repaired"] = True
            return ChunkExtract.model_validate(coerced).model_dump()
        except JobCancelled:
            raise
        except Exception as e:  # noqa: BLE001 — 校验/JSON 统一重试
            last_err = e
    raise ValueError(f"extract_failed:{chunk['id']}:{last_err}")


def run_extract(
    paths: ProjectPaths,
    llm: LlmClient,
    max_retries: int,
    skip_bad: bool,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    chunks = [
        json.loads(line)
        for line in paths.chunks_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total = len(chunks)
    errors: list[dict] = []
    error_msgs: list[str] = []
    low_quality: list[dict] = []
    done = 0
    succeeded = 0

    def _report() -> None:
        if on_progress is not None:
            on_progress(done, total)

    _report()
    for chunk in chunks:
        if should_cancel and should_cancel():
            raise JobCancelled("extract")
        dest = paths.extract_chunk_json(chunk["chapter_id"], chunk["id"])
        if dest.exists():
            done += 1
            succeeded += 1
            _report()
            continue
        try:
            data = extract_chunk(
                chunk,
                llm,
                max_retries=max_retries,
                should_cancel=should_cancel,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            quality = data.get("quality") or {}
            if quality.get("missing_evidence_count", 0) > 0:
                low_quality.append(
                    {
                        "chunk_id": chunk.get("chunk_id") or chunk["id"],
                        "chapter_id": chunk["chapter_id"],
                        "missing_evidence_count": quality.get("missing_evidence_count"),
                        "warnings": quality.get("warnings") or [],
                    }
                )
            done += 1
            succeeded += 1
            _report()
        except JobCancelled:
            raise
        except Exception as e:  # noqa: BLE001
            err = {
                "chunk_id": chunk.get("chunk_id") or chunk["id"],
                "chapter_id": chunk["chapter_id"],
                "error": "json_schema_validation_failed",
                "detail": str(e),
                "retry_count": max_retries + 1,
                "skipped": bool(skip_bad),
            }
            errors.append(err)
            error_msgs.append(str(e))
            if not skip_bad:
                raise
            done += 1
            _report()

    report = {
        "chunk_count": total,
        "succeeded": succeeded,
        "failed": len(errors),
        "low_quality_count": len(low_quality),
        "skip_bad_chunks": skip_bad,
    }
    paths.extract_dir.mkdir(parents=True, exist_ok=True)
    paths.extract_report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.extract_errors_json.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (paths.extract_dir / "low_quality_chunks.json").write_text(
        json.dumps(low_quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"total": total, "done": min(done, total), "errors": error_msgs, "report": report}
