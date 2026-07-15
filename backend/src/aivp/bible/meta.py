from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.bible.overlay import merge_bible
from aivp.schemas import REQUIRED_BIBLE_KEYS

REVIEW_STATUSES = ("draft", "needs_review", "approved", "needs_revision", "locked")


def default_block_meta(block: str) -> dict[str, Any]:
    return {
        "block": block,
        "review_status": "needs_review",
        "generated_by": "auto",
        "source_refs": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "system",
        "locked": False,
        "notes": [],
    }


def ensure_bible_meta(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    base = copy.deepcopy(meta) if meta else {}
    blocks = base.get("blocks") if isinstance(base.get("blocks"), dict) else {}
    for key in REQUIRED_BIBLE_KEYS:
        if key not in blocks or not isinstance(blocks[key], dict):
            blocks[key] = default_block_meta(key)
        else:
            blocks[key].setdefault("block", key)
            blocks[key].setdefault("review_status", "needs_review")
            blocks[key].setdefault("generated_by", "auto")
            blocks[key].setdefault("source_refs", [])
            blocks[key].setdefault("locked", False)
            blocks[key].setdefault("notes", [])
    base["schema_version"] = 3
    base["blocks"] = blocks
    base.setdefault("reviews", [])
    return base


def persist_merged_bible(
    *,
    auto_path: Path,
    overlay_path: Path,
    merged_path: Path,
    meta_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    auto = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.exists() else {}
    overlay = json.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path.exists() else {}
    meta = ensure_bible_meta(
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    )
    # Locked blocks: keep auto from being overridden by re-assemble through overlay priority —
    # if locked, force overlay to contain current merged content for that block after assemble.
    merged = merge_bible(auto, overlay)
    for key, block_meta in meta["blocks"].items():
        if block_meta.get("locked") and key in merged:
            # Preserve locked content already in overlay if present; else snapshot merged.
            if key not in overlay:
                overlay[key] = copy.deepcopy(merged[key])
                overlay_path.parent.mkdir(parents=True, exist_ok=True)
                overlay_path.write_text(
                    json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                merged = merge_bible(auto, overlay)
    merged["schema_version"] = 3
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged, meta


def set_block_review(
    meta: dict[str, Any],
    *,
    block: str,
    action: str,
    note: str = "",
) -> dict[str, Any]:
    meta = ensure_bible_meta(meta)
    if block not in meta["blocks"]:
        raise KeyError(block)
    status_map = {
        "approve": "approved",
        "reject": "needs_revision",
        "needs_review": "needs_review",
        "draft": "draft",
    }
    if action not in status_map:
        raise ValueError(f"unknown_action:{action}")
    entry = meta["blocks"][block]
    if entry.get("locked") and action != "approve":
        # unlocking is separate
        pass
    entry["review_status"] = status_map[action]
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    entry["updated_by"] = "user"
    if note:
        entry.setdefault("notes", []).append(
            {"note": note, "at": entry["updated_at"], "action": action}
        )
    meta.setdefault("reviews", []).append(
        {
            "id": f"review_{len(meta['reviews'])+1:04d}",
            "target_type": "story_bible_block",
            "target_id": block,
            "action": action,
            "note": note,
            "created_at": entry["updated_at"],
        }
    )
    return meta


def set_block_lock(meta: dict[str, Any], *, block: str, locked: bool) -> dict[str, Any]:
    meta = ensure_bible_meta(meta)
    if block not in meta["blocks"]:
        raise KeyError(block)
    entry = meta["blocks"][block]
    entry["locked"] = locked
    if locked:
        entry["review_status"] = "locked"
    elif entry.get("review_status") == "locked":
        entry["review_status"] = "approved"
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    entry["updated_by"] = "user"
    return meta
