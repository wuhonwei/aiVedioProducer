from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIVP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    data_root: Path = Path("data")
    db_url: str = "sqlite:///./data/aivp.db"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:14b"
    chunk_size: int = 4000
    chunk_overlap: int = 500
    extract_max_retries: int = 2
    skip_bad_chunks: bool = True
    extract_workers: int = 4
    extract_progress_every: int = 10
    volume_max_chars: int = 80_000
    volume_max_chapters: int = 40
    timeline_page_size: int = 50
    api_page_size: int = 50
    enrich_event_window: int = 40
    enrich_require_distinct_characters: bool = True
    enrich_top_characters: int = 8
    enrich_top_locations: int = 8
    enrich_top_props: int = 6
    enrich_top_factions: int = 4
    enrich_strict: bool = False
    enrich_force: bool = False
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    shot_batch_size: int = 8
    shot_strict: bool = False
    shot_force: bool = False
    # If false, missing DeepSeek key skips shot stage with warning instead of failing.
    shot_require_deepseek: bool = False
    # Visual / LoRA layer
    image_backend: str = "stub"  # stub | comfy
    comfy_base_url: str = "http://127.0.0.1:8188"
    comfy_checkpoint: str = ""
    comfy_timeout_sec: float = 180.0
    lora_train_cmd: str = ""
    visual_candidate_count: int = 8
    ollama_vision_model: str = "qwen2.5vl:7b"
    visual_qa_pass_rate: float = 0.60
    visual_qa_max_rounds: int = 3
    # Auto trainset bootstrap
    bootstrap_lock_candidate_count: int = 14
    bootstrap_lock_batch_retries: int = 3
    bootstrap_slot_retries: int = 3
    bootstrap_desc_rewrite_retries: int = 3
    bootstrap_archive_top_k: int = 3
    bootstrap_plain_background: bool = True
    # Location LoRA bootstrap (empty-scene plates)
    location_bootstrap_lock_count: int = 14
    location_bootstrap_lock_batch_retries: int = 3
    location_bootstrap_slot_retries: int = 3
    location_bootstrap_desc_rewrite_retries: int = 3
    location_bootstrap_archive_top_k: int = 3
    location_lora_strength: float = 0.7
