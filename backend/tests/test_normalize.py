from aivp.pipeline.normalize import normalize_entities, run_normalize
from pathlib import Path
import json


def test_normalize_merges_aliases():
    extracts = [
        {"characters": [{"name": "李青云", "aliases": ["青云"]}], "locations": [], "factions": [], "props": []},
        {"characters": [{"name": "青云", "aliases": []}], "locations": [], "factions": [], "props": []},
    ]
    result = normalize_entities(extracts)
    entities = result["entities"]
    names = [c["name"] for c in entities["characters"]]
    assert names.count("李青云") == 1
    assert "青云" in entities["characters"][0]["aliases"]
    assert entities["characters"][0]["merge_history"]


def test_normalize_sources_and_first_appearance():
    extracts = [
        {
            "_chapter_id": "chapter_0001",
            "_chunk_id": "0001",
            "characters": [{"name": "林澈", "aliases": []}],
            "locations": [],
            "factions": [],
            "props": [],
        },
        {
            "_chapter_id": "chapter_0002",
            "_chunk_id": "0001",
            "characters": [{"name": "林澈", "aliases": ["林捕快"]}],
            "locations": [],
            "factions": [],
            "props": [],
        },
    ]
    result = normalize_entities(extracts)
    char = result["entities"]["characters"][0]
    assert char["first_appearance"] == "chapter_0001"
    assert "chapter_0001_chunk_0001" in char["sources"]
    assert "chapter_0002_chunk_0001" in char["sources"]


def test_normalize_writes_uncertain_report(tmp_path: Path):
    extract_dir = tmp_path / "04_extract" / "chapter_0001"
    extract_dir.mkdir(parents=True)
    (extract_dir / "0001.json").write_text(
        json.dumps(
            {
                "characters": [
                    {"name": "林澈", "aliases": []},
                    {"name": "林澈啊", "aliases": []},
                ],
                "locations": [],
                "factions": [],
                "props": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "05_normalize" / "entities.json"
    run_normalize(tmp_path / "04_extract", out)
    assert out.exists()
    assert (out.parent / "normalize_report.json").exists()
    assert (out.parent / "uncertain_entities.json").exists()
    assert (out.parent / "candidate_pairs.json").exists()
    entities = json.loads(out.read_text(encoding="utf-8"))
    assert entities["characters"][0]["sources"]
    assert entities["characters"][0]["first_appearance"] == "chapter_0001"
