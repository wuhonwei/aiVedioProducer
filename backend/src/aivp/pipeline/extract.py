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
    "键必须齐全: characters, locations, factions, props, events, "
    "foreshadowing, visual_cues, voice_cues, adaptation_notes。"
    "characters/locations/factions/props 必须是对象数组，每项含 name(string) 与 aliases(string[])。"
    "events 必须是对象数组，每项至少含 summary(string)。"
    "foreshadowing 必须是对象数组，每项至少含 note(string)。"
    "visual_cues/voice_cues/adaptation_notes 必须是 string 数组。"
    "缺信息用空数组。"
)

EXAMPLE = (
    '{"characters":[{"name":"林砚之","aliases":["少年"]}],'
    '"locations":[{"name":"青川渡","aliases":[]}],'
    '"factions":[],"props":[{"name":"玉佩","aliases":[]}],'
    '"events":[{"summary":"林砚之抵达青川渡寻找陈守义"}],'
    '"foreshadowing":[{"note":"未写完的家信"}],'
    '"visual_cues":["江雾笼罩的青石渡口"],'
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
        "请按 schema 抽取上述字段。示例形状:\n"
        f"{EXAMPLE}"
    )
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        if should_cancel and should_cancel():
            raise JobCancelled(chunk["id"])
        try:
            raw = llm.complete_json(
                SYSTEM,
                user if _ == 0 else user + "\n请严格修复为合法 JSON schema。",
                should_cancel=should_cancel,
            )
            coerced = coerce_extract(raw)
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
    errors: list[str] = []
    done = 0

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
            done += 1
            _report()
        except JobCancelled:
            raise
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            if not skip_bad:
                raise
            done += 1
            _report()
    return {"total": total, "done": min(done, total), "errors": errors}
