import json
import re
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.strip().lower())


def _similar(a: str, b: str) -> float:
    """Dice coefficient on character bigrams — no extra dependency."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        return 0.75 + 0.2 * (len(shorter) / len(longer))
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0
    a2 = {a[i : i + 2] for i in range(len(a) - 1)}
    b2 = {b[i : i + 2] for i in range(len(b) - 1)}
    inter = len(a2 & b2)
    return (2.0 * inter) / (len(a2) + len(b2)) if (a2 and b2) else 0.0


def _source_id(chapter_id: str, chunk_id: str) -> str:
    if chapter_id and chunk_id and not str(chunk_id).startswith(str(chapter_id)):
        # Prefer global chunk id when local id (0001) is provided.
        if re.fullmatch(r"\d{4}", str(chunk_id)):
            return f"{chapter_id}_chunk_{chunk_id}"
    return str(chunk_id or chapter_id or "")


def _merge_group(items: list[dict], entity_type: str) -> tuple[list[dict], list[dict]]:
    by_key: dict[str, dict] = {}
    alias_to_canonical: dict[str, str] = {}
    uncertain: list[dict] = []

    for item in items:
        name = item["name"].strip()
        aliases = [a.strip() for a in item.get("aliases", []) if a and str(a).strip()]
        sources = item.get("sources") or []
        evidence = item.get("evidence") or ""
        first_appearance = item.get("first_appearance") or ""

        canon = alias_to_canonical.get(name, name)
        for a in aliases:
            if a in alias_to_canonical:
                canon = alias_to_canonical[a]

        if canon not in by_key:
            by_key[canon] = {
                "id": f"ent_{len(by_key)+1:04d}",
                "type": entity_type,
                "canonical_name": canon,
                "name": canon,
                "aliases": [],
                "sources": [],
                "first_appearance": first_appearance or "",
                "confidence": 0.95,
                "merge_history": [],
                "review_status": "auto_merged",
                "evidence": evidence,
            }
        entry = by_key[canon]
        for a in [name, *aliases]:
            if a != entry["name"] and a not in entry["aliases"]:
                entry["aliases"].append(a)
                if a != name or aliases:
                    entry["merge_history"].append(
                        {
                            "from": a,
                            "reason": "alias_exact_match",
                            "confidence": 0.95,
                        }
                    )
            alias_to_canonical[a] = entry["name"]
        for s in sources:
            if s and s not in entry["sources"]:
                entry["sources"].append(s)
        if first_appearance and not entry.get("first_appearance"):
            entry["first_appearance"] = first_appearance
        if evidence and not entry.get("evidence"):
            entry["evidence"] = evidence

    # Fuzzy uncertain pairs — bucket by first char + length band to avoid O(n^2) on huge sets.
    names = list(by_key.keys())
    buckets: dict[tuple[str, int], list[str]] = {}
    for name in names:
        key = (name[:1] if name else "", len(name) // 2)
        buckets.setdefault(key, []).append(name)
    seen_pairs: set[tuple[str, str]] = set()
    for group in buckets.values():
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                score = _similar(left, right)
                if score < 0.72 or score >= 0.98:
                    continue
                pair = tuple(sorted((left, right)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                signals = ["string_similarity"]
                left_src = set(by_key[left].get("sources") or [])
                right_src = set(by_key[right].get("sources") or [])
                left_ch = {s.split("_chunk_")[0] for s in left_src if "_chunk_" in s}
                right_ch = {s.split("_chunk_")[0] for s in right_src if "_chunk_" in s}
                if left_ch & right_ch:
                    signals.append("same_chapter")
                uncertain.append(
                    {
                        "left": left,
                        "right": right,
                        "type": entity_type,
                        "score": round(score, 3),
                        "signals": signals,
                        "reason": "string_similarity_bucketed",
                        "recommendation": "merge" if score >= 0.85 else "review",
                        "review_status": "pending",
                        "left_id": by_key[left]["id"],
                        "right_id": by_key[right]["id"],
                    }
                )
                by_key[left]["confidence"] = min(by_key[left]["confidence"], 0.7)
                by_key[right]["confidence"] = min(by_key[right]["confidence"], 0.7)
                by_key[left]["review_status"] = "needs_review"
                by_key[right]["review_status"] = "needs_review"

    return list(by_key.values()), uncertain


def _seed_items_from_extract(
    ex: dict,
    *,
    chapter_id: str = "",
    chunk_id: str = "",
) -> dict[str, list]:
    source = _source_id(chapter_id, chunk_id)
    first_appearance = chapter_id or ""
    buckets: dict[str, list] = {
        "characters": [],
        "locations": [],
        "factions": [],
        "props": [],
    }
    for k in buckets:
        for item in ex.get(k, []) or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            seeded = dict(item)
            sources = list(seeded.get("sources") or [])
            if source and source not in sources:
                sources.append(source)
            seeded["sources"] = sources
            if first_appearance and not seeded.get("first_appearance"):
                seeded["first_appearance"] = first_appearance
            buckets[k].append(seeded)
    return buckets


def normalize_entities(extracts: list[dict]) -> dict:
    buckets: dict[str, list] = {
        "characters": [],
        "locations": [],
        "factions": [],
        "props": [],
    }
    for ex in extracts:
        chapter_id = str(ex.get("_chapter_id") or "")
        chunk_id = str(ex.get("_chunk_id") or "")
        seeded = _seed_items_from_extract(ex, chapter_id=chapter_id, chunk_id=chunk_id)
        for k in buckets:
            buckets[k].extend(seeded[k])

    entities: dict[str, list] = {}
    all_uncertain: list[dict] = []
    all_candidates: list[dict] = []
    auto_merged = 0
    for k, items in buckets.items():
        merged, uncertain = _merge_group(items, k[:-1] if k.endswith("s") else k)
        entities[k] = merged
        all_uncertain.extend(uncertain)
        all_candidates.extend(uncertain)
        auto_merged += sum(1 for e in merged if e.get("merge_history"))

    return {
        "entities": entities,
        "uncertain_entities": all_uncertain,
        "candidate_pairs": all_candidates,
        "auto_merged": auto_merged,
    }


def _load_extracts(extract_dir: Path, chapter_ids: set[str] | None = None) -> list[dict]:
    extracts: list[dict] = []
    for path in sorted(extract_dir.glob("*/*.json")):
        if path.name in {"extract_report.json", "errors.json", "low_quality_chunks.json"}:
            continue
        if chapter_ids is not None and path.parent.name not in chapter_ids:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["_chapter_id"] = path.parent.name
            data["_chunk_id"] = path.stem
            extracts.append(data)
    return extracts


def run_normalize(extract_dir: Path, out_json: Path) -> dict:
    extracts = _load_extracts(extract_dir)
    result = normalize_entities(extracts)
    entities = result["entities"]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_json.parent / "uncertain_entities.json").write_text(
        json.dumps(result["uncertain_entities"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_json.parent / "candidate_pairs.json").write_text(
        json.dumps(result["candidate_pairs"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "characters": len(entities.get("characters") or []),
        "locations": len(entities.get("locations") or []),
        "props": len(entities.get("props") or []),
        "factions": len(entities.get("factions") or []),
        "entity_counts": {k: len(v) for k, v in entities.items()},
        "auto_merged": result.get("auto_merged", 0),
        "uncertain": len(result["uncertain_entities"]),
        "uncertain_count": len(result["uncertain_entities"]),
        "warnings": [],
    }
    (out_json.parent / "normalize_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entities


def normalize_extracts_for_chapters(
    extract_dir: Path,
    chapter_ids: set[str],
) -> list[dict]:
    return _load_extracts(extract_dir, chapter_ids)


def run_normalize_volume(
    extract_dir: Path,
    out_json: Path,
    chapter_ids: list[str],
) -> dict:
    extracts = normalize_extracts_for_chapters(extract_dir, set(chapter_ids))
    result = normalize_entities(extracts)
    entities = result["entities"]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_json.parent / "uncertain_entities.json").write_text(
        json.dumps(result["uncertain_entities"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_json.parent / "candidate_pairs.json").write_text(
        json.dumps(result["candidate_pairs"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return entities


def merge_volume_entities(volume_entity_maps: list[dict]) -> dict:
    """Merge per-volume entities.json dicts into a global entities map."""
    buckets: dict[str, list] = {
        "characters": [],
        "locations": [],
        "factions": [],
        "props": [],
    }
    for entities in volume_entity_maps:
        for k in buckets:
            for item in entities.get(k) or []:
                if isinstance(item, dict) and item.get("name"):
                    # Flatten to seed form for re-merge
                    buckets[k].append(
                        {
                            "name": item.get("canonical_name") or item.get("name"),
                            "aliases": list(item.get("aliases") or []),
                            "evidence": item.get("evidence") or "",
                            "sources": list(item.get("sources") or []),
                            "first_appearance": item.get("first_appearance") or "",
                        }
                    )
    # Re-run alias+bucket merge across volumes
    flat_extracts = [{k: buckets[k] for k in buckets}]
    # normalize_entities expects list of extract-shaped dicts
    return normalize_entities(flat_extracts)


def apply_entity_merge(
    entities: dict,
    uncertain: list[dict],
    *,
    left: str,
    right: str,
    entity_type: str,
    accept: bool,
) -> tuple[dict, list[dict]]:
    """Merge or reject a pending uncertain pair. Mutates copies."""
    type_key = entity_type if entity_type.endswith("s") else entity_type + "s"
    if type_key not in entities:
        type_key = {
            "character": "characters",
            "location": "locations",
            "faction": "factions",
            "prop": "props",
        }.get(entity_type, entity_type)

    remaining = [
        u
        for u in uncertain
        if not (
            {u.get("left"), u.get("right")} == {left, right}
            and (u.get("type") == entity_type or u.get("type") + "s" == type_key)
        )
    ]
    if not accept:
        return entities, remaining

    group = list(entities.get(type_key, []))
    left_ent = next((e for e in group if e.get("name") == left or e.get("canonical_name") == left), None)
    right_ent = next((e for e in group if e.get("name") == right or e.get("canonical_name") == right), None)
    if not left_ent or not right_ent or left_ent is right_ent:
        return entities, remaining

    keep, drop = left_ent, right_ent
    for a in [drop.get("name"), *(drop.get("aliases") or [])]:
        if a and a != keep["name"] and a not in keep.get("aliases", []):
            keep.setdefault("aliases", []).append(a)
    for s in drop.get("sources") or []:
        if s and s not in keep.get("sources", []):
            keep.setdefault("sources", []).append(s)
    if not keep.get("first_appearance") and drop.get("first_appearance"):
        keep["first_appearance"] = drop["first_appearance"]
    keep.setdefault("merge_history", []).append(
        {"from": drop.get("name"), "reason": "manual_merge", "confidence": 1.0}
    )
    keep["review_status"] = "manual_merged"
    keep["confidence"] = 1.0
    entities[type_key] = [e for e in group if e is not drop]
    return entities, remaining
