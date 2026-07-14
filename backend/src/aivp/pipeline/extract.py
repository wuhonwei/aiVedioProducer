import json
from pathlib import Path
from aivp.llm.base import LlmClient
from aivp.paths import ProjectPaths
from aivp.schemas import ChunkExtract

SYSTEM = (
    "你是国风长篇结构化抽取器。只输出 JSON，键必须匹配给定 schema。"
    "缺信息用空数组。不要输出 markdown。"
)


def extract_chunk(chunk: dict, llm: LlmClient, max_retries: int = 2) -> dict:
    user = (
        f"章节:{chunk.get('chapter_title','')}\n"
        f"正文:\n{chunk['text']}\n"
        "请抽取 characters/locations/factions/props/events/"
        "foreshadowing/visual_cues/voice_cues/adaptation_notes"
    )
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            raw = llm.complete_json(SYSTEM, user if _ == 0 else user + "\n请严格修复为合法 JSON schema。")
            return ChunkExtract.model_validate(raw).model_dump()
        except Exception as e:  # noqa: BLE001 — 校验/JSON 统一重试
            last_err = e
    raise ValueError(f"extract_failed:{chunk['id']}:{last_err}")


def run_extract(paths: ProjectPaths, llm: LlmClient, max_retries: int, skip_bad: bool) -> dict:
    chunks = [
        json.loads(line)
        for line in paths.chunks_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    errors: list[str] = []
    done = 0
    for chunk in chunks:
        dest = paths.extract_chunk_json(chunk["chapter_id"], chunk["id"])
        if dest.exists():
            done += 1
            continue
        try:
            data = extract_chunk(chunk, llm, max_retries=max_retries)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            if not skip_bad:
                raise
    return {"total": len(chunks), "done": done, "errors": errors}
