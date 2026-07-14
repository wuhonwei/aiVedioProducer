from aivp.pipeline.coerce_extract import coerce_extract
from aivp.pipeline.extract import extract_chunk
from aivp.llm.fake import FakeLlm
from aivp.schemas import ChunkExtract


def test_coerce_accepts_messy_ollama_shapes():
    raw = {
        "characters": ["林砚之", {"name": "陈守义", "aliases": ["守义"]}],
        "locations": [{"title": "青川渡"}],
        "factions": [],
        "props": [{"item": "玉佩", "usage": "信物"}],
        "events": [
            "林砚之抵达渡口",
            {"description": "雾锁青川渡", "type": "atmosphere"},
        ],
        "foreshadowing": ["未写完的家信", {"note": "寻找陈守义"}],
        "visual_cues": [
            {"description": "湿冷白雾"},
            {"cue": "青石板路"},
        ],
        "voice_cues": [{"dialogue": "去青川渡，找陈守义"}],
        "adaptation_notes": [{"note": "开场长镜头", "type": "镜头"}],
    }
    coerced = coerce_extract(raw)
    model = ChunkExtract.model_validate(coerced)
    assert model.characters[0].name == "林砚之"
    assert model.props[0].name == "玉佩"
    assert model.events[0]["summary"] == "林砚之抵达渡口"
    assert model.events[1]["summary"] == "雾锁青川渡"
    assert "湿冷白雾" in model.visual_cues
    assert model.adaptation_notes[0] == "开场长镜头"


def test_extract_chunk_coerces_before_validate():
    llm = FakeLlm(
        default={
            "characters": ["林砚之"],
            "locations": ["青川渡"],
            "factions": [],
            "props": [{"item": "玉佩"}],
            "events": ["抵达渡口"],
            "foreshadowing": ["家信"],
            "visual_cues": [{"cue": "江雾"}],
            "voice_cues": [],
            "adaptation_notes": [],
        }
    )
    out = extract_chunk(
        {"id": "0001", "chapter_title": "雾锁渡口", "text": "林砚之站在雾里。"},
        llm,
    )
    assert out["characters"][0]["name"] == "林砚之"
    assert out["events"][0]["summary"] == "抵达渡口"
