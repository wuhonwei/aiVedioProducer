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
        self.clean_metadata_json = self.stages_dir / "01_clean" / "metadata.json"
        self.clean_report_json = self.stages_dir / "01_clean" / "clean_report.json"
        self.chapters_json = self.stages_dir / "02_chapters" / "chapters.json"
        self.chapter_report_json = self.stages_dir / "02_chapters" / "chapter_report.json"
        self.chunks_jsonl = self.stages_dir / "03_chunks" / "chunks.jsonl"
        self.chunk_report_json = self.stages_dir / "03_chunks" / "chunk_report.json"
        self.extract_dir = self.stages_dir / "04_extract"
        self.extract_report_json = self.extract_dir / "extract_report.json"
        self.extract_errors_json = self.extract_dir / "errors.json"
        self.entities_json = self.stages_dir / "05_normalize" / "entities.json"
        self.normalize_dir = self.stages_dir / "05_normalize"
        self.uncertain_entities_json = self.normalize_dir / "uncertain_entities.json"
        self.candidate_pairs_json = self.normalize_dir / "candidate_pairs.json"
        self.normalize_report_json = self.normalize_dir / "normalize_report.json"
        self.merged_bible_json = self.stages_dir / "09_bible" / "story_bible.merged.json"
        self.bible_meta_json = self.stages_dir / "09_bible" / "story_bible.meta.json"
        self.asset_plan_json = self.root / "assets" / "asset_plan.json"
        self.shots_dir = self.root / "shots"
        self.enrich_dir = self.stages_dir / "06_enrich_assets"
        self.majors_json = self.enrich_dir / "majors.json"
        self.assets_json = self.enrich_dir / "assets.json"
        self.events_enriched_json = self.enrich_dir / "events_enriched.json"
        self.events_json = self.stages_dir / "07_timeline" / "events.json"
        self.arcs_json = self.stages_dir / "08_arcs" / "arcs.json"
        self.auto_bible_json = self.stages_dir / "09_bible" / "story_bible.auto.json"
        self.shot_script_dir = self.stages_dir / "10_shot_script"
        self.shot_script_json = self.shot_script_dir / "shot_script.json"
        self.overlay_json = self.overlays_dir / "story_bible.overlay.json"

    def ensure(self) -> None:
        for d in (
            self.raw_dir,
            self.stages_dir / "01_clean",
            self.stages_dir / "02_chapters",
            self.stages_dir / "03_chunks",
            self.extract_dir,
            self.stages_dir / "05_normalize",
            self.enrich_dir,
            self.stages_dir / "07_timeline",
            self.stages_dir / "08_arcs",
            self.stages_dir / "09_bible",
            self.shot_script_dir,
            self.overlays_dir,
            self.exports_dir,
            self.root / "assets",
            self.shots_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def extract_chunk_json(self, chapter_id: str, chunk_id: str) -> Path:
        return self.extract_dir / chapter_id / f"{chunk_id}.json"
