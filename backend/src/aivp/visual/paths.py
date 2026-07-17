from __future__ import annotations

from pathlib import Path


class VisualPaths:
    def __init__(self, data_root: Path, project_id: str):
        self.data_root = Path(data_root)
        self.project_id = project_id
        self.root = self.data_root / "projects" / project_id / "visual"
        self.characters_dir = self.root / "characters"
        self.comfy_dir = self.root / "comfy"
        self.jobs_dir = self.root / "jobs"

    def ensure(self) -> None:
        for d in (self.root, self.characters_dir, self.comfy_dir, self.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def character_dir(self, character_id: str) -> Path:
        return self.characters_dir / character_id

    def profile_json(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "profile.json"

    def candidates_dir(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "candidates"

    def curated_dir(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "curated"

    def lora_dir(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "lora"

    def generations_dir(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "generations"

    def sheets_dir(self, character_id: str) -> Path:
        return self.character_dir(character_id) / "sheets"

    def ensure_character(self, character_id: str) -> None:
        for d in (
            self.character_dir(character_id),
            self.candidates_dir(character_id),
            self.curated_dir(character_id),
            self.lora_dir(character_id),
            self.generations_dir(character_id),
            self.sheets_dir(character_id),
        ):
            d.mkdir(parents=True, exist_ok=True)
