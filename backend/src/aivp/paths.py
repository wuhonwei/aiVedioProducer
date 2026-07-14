from pathlib import Path


class ProjectPaths:
    def __init__(self, data_root: Path, project_id: str):
        self.root = data_root / "projects" / project_id
        self.raw_dir = self.root / "raw"
        self.stages_dir = self.root / "stages"
        self.overlays_dir = self.root / "overlays"
        self.exports_dir = self.root / "exports"
        self.source_txt = self.raw_dir / "source.txt"
        self.clean_txt = self.stages_dir / "01_clean" / "cleaned.txt"
        self.chapters_json = self.stages_dir / "02_chapters" / "chapters.json"
        self.chunks_jsonl = self.stages_dir / "03_chunks" / "chunks.jsonl"
        self.extract_dir = self.stages_dir / "04_extract"
        self.entities_json = self.stages_dir / "05_normalize" / "entities.json"
        self.events_json = self.stages_dir / "06_timeline" / "events.json"
        self.arcs_json = self.stages_dir / "07_arcs" / "arcs.json"
        self.auto_bible_json = self.stages_dir / "08_bible" / "story_bible.auto.json"
        self.overlay_json = self.overlays_dir / "story_bible.overlay.json"

    def ensure(self) -> None:
        for d in (
            self.raw_dir,
            self.stages_dir / "01_clean",
            self.stages_dir / "02_chapters",
            self.stages_dir / "03_chunks",
            self.extract_dir,
            self.stages_dir / "05_normalize",
            self.stages_dir / "06_timeline",
            self.stages_dir / "07_arcs",
            self.stages_dir / "08_bible",
            self.overlays_dir,
            self.exports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def extract_chunk_json(self, chapter_id: str, chunk_id: str) -> Path:
        return self.extract_dir / chapter_id / f"{chunk_id}.json"
