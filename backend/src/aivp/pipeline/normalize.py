import json
from pathlib import Path


def _merge_group(items: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    alias_to_canonical: dict[str, str] = {}
    for item in items:
        name = item["name"].strip()
        aliases = [a.strip() for a in item.get("aliases", []) if a.strip()]
        canon = alias_to_canonical.get(name, name)
        for a in aliases:
            if a in alias_to_canonical:
                canon = alias_to_canonical[a]
        if canon not in by_key:
            by_key[canon] = {"id": f"ent_{len(by_key)+1:04d}", "name": canon, "aliases": []}
        entry = by_key[canon]
        for a in [name, *aliases]:
            if a != entry["name"] and a not in entry["aliases"]:
                entry["aliases"].append(a)
            alias_to_canonical[a] = entry["name"]
    return list(by_key.values())


def normalize_entities(extracts: list[dict]) -> dict:
    buckets = {"characters": [], "locations": [], "factions": [], "props": []}
    for ex in extracts:
        for k in buckets:
            buckets[k].extend(ex.get(k, []))
    return {k: _merge_group(v) for k, v in buckets.items()}


def run_normalize(extract_dir: Path, out_json: Path) -> dict:
    extracts: list[dict] = []
    for path in sorted(extract_dir.glob("*/*.json")):
        extracts.append(json.loads(path.read_text(encoding="utf-8")))
    entities = normalize_entities(extracts)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    return entities
