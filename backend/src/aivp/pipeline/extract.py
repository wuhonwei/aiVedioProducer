from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aivp.jobs.control import JobCancelled
from aivp.llm.base import LlmClient
from aivp.paths import ProjectPaths
from aivp.pipeline.coerce_extract import coerce_extract
from aivp.schemas import ChunkExtract

SYSTEM = (
    "你是国风长篇结构化抽取器。只输出 JSON 对象，不要 markdown。"
    "键必须齐全: summary, characters, locations, factions, props, events, "
    "foreshadowing, relationships, visual_cues, visual_candidates, voice_cues, adaptation_notes。"
    "不得编造原文未出现的信息；不确定则填 unknown 或空字符串；缺信息用空数组或空字符串。"
    "所有关键事实必须尽量提供 evidence 原文摘录。"
    "下方示例仅说明 JSON 字段形状，禁止照抄示例中的人名、地名与情节。"
    "characters 为对象数组，可含 name、aliases[]、identity_hint、appearance[]、personality[]、"
    "actions[]、emotion、evidence。"
    "locations 为对象数组，可含 name、aliases[]、description、atmosphere、evidence。"
    "factions/props 为对象数组，每项含 name、aliases[]、evidence。"
    "events 必须尽量包含 summary、participants、location、time_hint、cause、process、result、"
    "importance、visual_score、evidence，且必须来自当前正文。"
    "foreshadowing 为对象数组，每项至少含 note 与 evidence。"
    "visual_candidates 用于标记适合视频化的片段，含 scene、evidence、visual_score、reason。"
    "visual_cues/voice_cues/adaptation_notes 为 string 数组。"
)

EXAMPLE = (
    '{"summary":"本段发生的一件关键事",'
    '"characters":[{"name":"角色甲","aliases":["别称"],"evidence":"原文中出现角色甲的短句"}],'
    '"locations":[{"name":"地点甲","aliases":[],"evidence":"原文中出现地点甲的短句"}],'
    '"factions":[],"props":[{"name":"物件甲","aliases":[],"evidence":"原文中出现物件甲的短句"}],'
    '"events":[{"summary":"角色甲在地点甲完成某动作","evidence":"支撑该事件的原文短句"}],'
    '"foreshadowing":[{"note":"后文可能回收的伏笔","evidence":"伏笔相关原文短句"}],'
    '"relationships":[],'
    '"visual_cues":["可视觉化的环境描写"],'
    '"visual_candidates":[{"scene":"一段可拍电影的画面","evidence":"画面依据原文","visual_score":0.9}],'
    '"voice_cues":["可听到的声音线索"],'
    '"adaptation_notes":["改编提示一条"]}'
)

LEAKED_EXAMPLE_SUMMARIES = frozenset(
    {
        "林砚之抵达青川渡寻找陈守义",
        "林砚之抵达青川渡",
    }
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
            chunk_text = str(chunk.get("text") or "")
            cleaned_events = []
            for ev in coerced.get("events") or []:
                if not isinstance(ev, dict):
                    continue
                summary = str(ev.get("summary") or "").strip()
                if (
                    summary in LEAKED_EXAMPLE_SUMMARIES
                    and "林砚之" not in chunk_text
                    and "青川渡" not in chunk_text
                ):
                    continue
                cleaned_events.append(ev)
            coerced["events"] = cleaned_events
            return ChunkExtract.model_validate(coerced).model_dump()
        except JobCancelled:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise ValueError(f"extract_failed:{chunk['id']}:{last_err}")


def _process_one(
    chunk: dict,
    paths: ProjectPaths,
    llm: LlmClient,
    max_retries: int,
) -> tuple[str, dict | None, dict | None, str | None]:
    """Return (status, low_quality|None, error|None, err_msg|None). status: ok|skip|err"""
    dest = paths.extract_chunk_json(chunk["chapter_id"], chunk["id"])
    if dest.exists():
        return "skip", None, None, None
    data = extract_chunk(chunk, llm, max_retries=max_retries)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    quality = data.get("quality") or {}
    low = None
    if quality.get("missing_evidence_count", 0) > 0:
        low = {
            "chunk_id": chunk.get("chunk_id") or chunk["id"],
            "chapter_id": chunk["chapter_id"],
            "missing_evidence_count": quality.get("missing_evidence_count"),
            "warnings": quality.get("warnings") or [],
        }
    return "ok", low, None, None


def run_extract(
    paths: ProjectPaths,
    llm: LlmClient,
    max_retries: int,
    skip_bad: bool,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    workers: int = 4,
    progress_every: int = 10,
    report_json: Path | None = None,
    errors_json: Path | None = None,
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
    lock = threading.Lock()
    last_report = 0.0
    workers = max(1, int(workers or 1))
    progress_every = max(1, int(progress_every or 1))

    def _maybe_report(force: bool = False) -> None:
        nonlocal last_report
        if on_progress is None:
            return
        now = time.monotonic()
        if (
            force
            or done == total
            or done % progress_every == 0
            or total <= progress_every
            or (now - last_report) >= 5.0
        ):
            on_progress(done, total)
            last_report = now

    with lock:
        if on_progress is not None:
            on_progress(0, total)
            last_report = time.monotonic()

    pending = []
    for chunk in chunks:
        dest = paths.extract_chunk_json(chunk["chapter_id"], chunk["id"])
        if dest.exists():
            with lock:
                done += 1
                succeeded += 1
                _maybe_report()
        else:
            pending.append(chunk)

    if should_cancel and should_cancel():
        raise JobCancelled("extract")

    def _work(chunk: dict) -> tuple[dict, str, dict | None, dict | None, str | None]:
        if should_cancel and should_cancel():
            raise JobCancelled("extract")
        try:
            status, low, err, msg = _process_one(chunk, paths, llm, max_retries)
            return chunk, status, low, err, msg
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
            return chunk, "err", None, err, str(e)

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_work, c) for c in pending]
            for fut in as_completed(futures):
                try:
                    _chunk, status, low, err, msg = fut.result()
                except JobCancelled:
                    for f in futures:
                        f.cancel()
                    raise
                with lock:
                    if status == "ok":
                        succeeded += 1
                        if low:
                            low_quality.append(low)
                    elif status == "err":
                        if err:
                            errors.append(err)
                        if msg:
                            error_msgs.append(msg)
                        if not skip_bad:
                            raise RuntimeError(msg or "extract_failed")
                    done += 1
                    _maybe_report()

    with lock:
        _maybe_report(force=True)

    already_done = total - len(pending)
    report = {
        "total": total,
        "chunk_count": total,
        "succeeded": succeeded,
        "failed": len(errors),
        "skipped": already_done,
        "low_quality_count": len(low_quality),
        "missing_evidence_chunks": low_quality,
        "low_quality_chunks": low_quality,
        "errors": errors,
        "skip_bad_chunks": skip_bad,
        "workers": workers,
    }
    paths.extract_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_json or paths.extract_report_json
    errors_path = errors_json or paths.extract_errors_json
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    errors_path.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (paths.extract_dir / "low_quality_chunks.json").write_text(
        json.dumps(low_quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"total": total, "done": min(done, total), "errors": error_msgs, "report": report}
