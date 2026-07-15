from pathlib import Path

from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths
from aivp.pipeline.shot_script import expand_events_with_llm, run_shot_script


def test_expand_events_produces_shots_with_fake_llm():
    events = [
        {
            "id": "evt0001",
            "chapter_id": "ch001",
            "summary": "林砚之抵达青川渡",
            "visual_beat": "江雾中少年下船",
            "camera_hint": "远景推近",
            "cast": ["林砚之"],
            "duration_hint_sec": 6,
        }
    ]
    llm = FakeLlm(
        default={
            "shots": [
                {
                    "event_id": "evt0001",
                    "order": 1,
                    "shot_type": "wide",
                    "camera": "航拍俯冲",
                    "action": "渡口全景",
                    "dialogue": "",
                    "duration_sec": 3,
                    "visual_prompt": "青川渡江雾，国风",
                    "audio_notes": "江水声",
                    "cast": ["林砚之"],
                    "location_name": "青川渡",
                }
            ]
        }
    )
    shots, warnings = expand_events_with_llm(events, None, llm, batch_size=4)
    assert not warnings
    assert len(shots) == 1
    assert shots[0]["shot_id"].startswith("EP001_")
    assert shots[0]["assets_required"]["characters"]
    assert shots[0]["review"]["status"] == "needs_review"
    assert shots[0]["visual_prompt"]


def test_run_shot_script_writes_file(tmp_path: Path):
    settings = Settings(data_root=tmp_path, deepseek_api_key="")
    paths = ProjectPaths(tmp_path, "s1")
    paths.ensure()
    paths.events_json.write_text(
        '[{"id":"evt0001","chapter_id":"ch001","summary":"相遇","cast":["甲"],'
        '"visual_beat":"雨夜对峙","camera_hint":"中景"}]',
        encoding="utf-8",
    )
    llm = FakeLlm(default={"shots": []})
    doc = run_shot_script(paths, settings, llm, force=True)
    assert paths.shot_script_json.exists()
    assert doc["shot_count"] >= 1
