from __future__ import annotations

from pathlib import Path


class VisualPaths:
    def __init__(self, data_root: Path, project_id: str):
        self.data_root = Path(data_root)
        self.project_id = project_id
        self.root = self.data_root / "projects" / project_id / "visual"
        self.characters_dir = self.root / "characters"
        self.locations_dir = self.root / "locations"
        self.comfy_dir = self.root / "comfy"
        self.jobs_dir = self.root / "jobs"

    def ensure(self) -> None:
        for d in (
            self.root,
            self.characters_dir,
            self.locations_dir,
            self.comfy_dir,
            self.jobs_dir,
        ):
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

    def location_dir(self, location_id: str) -> Path:
        return self.locations_dir / location_id

    def location_profile_json(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "profile.json"

    def location_candidates_dir(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "candidates"

    def location_curated_dir(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "curated"

    def location_lora_dir(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "lora"

    def location_generations_dir(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "generations"

    def location_sheets_dir(self, location_id: str) -> Path:
        return self.location_dir(location_id) / "sheets"

    def ensure_location(self, location_id: str) -> None:
        for d in (
            self.location_dir(location_id),
            self.location_candidates_dir(location_id),
            self.location_curated_dir(location_id),
            self.location_lora_dir(location_id),
            self.location_generations_dir(location_id),
            self.location_sheets_dir(location_id),
            self.location_dir(location_id) / "look_lock",
            self.location_dir(location_id) / "look_lock_archive",
        ):
            d.mkdir(parents=True, exist_ok=True)
