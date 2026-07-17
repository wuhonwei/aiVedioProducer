from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aivp.visual.paths import VisualPaths


def qa_tuning_path(vpaths: VisualPaths) -> Path:
    return vpaths.root / "qa_tuning.json"


def load_qa_tuning(vpaths: VisualPaths) -> dict[str, Any]:
    path = qa_tuning_path(vpaths)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_qa_tuning(vpaths: VisualPaths, data: dict[str, Any]) -> Path:
    path = qa_tuning_path(vpaths)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
