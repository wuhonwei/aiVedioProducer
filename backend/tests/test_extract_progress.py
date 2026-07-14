import json
from pathlib import Path

from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.pipeline.extract import run_extract


def test_run_extract_reports_progress(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    rows = [
        {"id": "0001", "chapter_id": "ch001", "chapter_title": "T", "text": "甲"},
        {"id": "0002", "chapter_id": "ch001", "chapter_title": "T", "text": "乙"},
    ]
    paths.chunks_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    llm = FakeLlm(
        default={
            "characters": [],
            "locations": [],
            "factions": [],
            "props": [],
            "events": [],
            "foreshadowing": [],
            "visual_cues": [],
            "voice_cues": [],
            "adaptation_notes": [],
        }
    )
    seen: list[tuple[int, int]] = []
    result = run_extract(
        paths,
        llm,
        max_retries=1,
        skip_bad=True,
        on_progress=lambda done, total: seen.append((done, total)),
    )
    assert result["done"] == 2
    assert result["total"] == 2
    assert (0, 2) in seen
    assert (1, 2) in seen
    assert (2, 2) in seen
