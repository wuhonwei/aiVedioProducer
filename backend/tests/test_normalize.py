from aivp.pipeline.normalize import normalize_entities


def test_normalize_merges_aliases():
    extracts = [
        {"characters": [{"name": "李青云", "aliases": ["青云"]}], "locations": [], "factions": [], "props": []},
        {"characters": [{"name": "青云", "aliases": []}], "locations": [], "factions": [], "props": []},
    ]
    entities = normalize_entities(extracts)
    names = [c["name"] for c in entities["characters"]]
    assert names.count("李青云") == 1
    assert "青云" in entities["characters"][0]["aliases"]
