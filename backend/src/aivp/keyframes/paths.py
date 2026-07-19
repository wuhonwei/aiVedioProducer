from __future__ import annotations

from pathlib import Path


class KeyframePaths:
    def __init__(self, data_root: Path, project_id: str):
        self.data_root = Path(data_root)
        self.project_id = project_id
        self.root = self.data_root / "projects" / project_id / "keyframes"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def shot_dir(self, shot_id: str) -> Path:
        return self.root / safe_shot_id(shot_id)

    def candidates_dir(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "candidates"

    def generation_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "generation.json"

    def selected_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "selected.json"

    def review_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "review.json"

    def ensure_shot(self, shot_id: str) -> None:
        self.ensure()
        self.shot_dir(shot_id).mkdir(parents=True, exist_ok=True)
        self.candidates_dir(shot_id).mkdir(parents=True, exist_ok=True)


def safe_shot_id(shot_id: str) -> str:
    s = (shot_id or "").strip()
    if not s or "/" in s or "\\" in s or ".." in s:
        raise ValueError(f"invalid_shot_id:{shot_id!r}")
    return s


def safe_filename(name: str) -> str:
    n = (name or "").strip()
    if not n or "/" in n or "\\" in n or ".." in n:
        raise ValueError(f"invalid_filename:{name!r}")
    if not n.lower().endswith(".png"):
        raise ValueError(f"invalid_filename:{name!r}")
    return n
