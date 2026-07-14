from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIVP_")
    data_root: Path = Path("data")
    db_url: str = "sqlite:///./data/aivp.db"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:14b"
    chunk_size: int = 1200
    chunk_overlap: int = 150
    extract_max_retries: int = 2
    skip_bad_chunks: bool = True
    enrich_top_characters: int = 8
    enrich_top_locations: int = 8
    enrich_top_props: int = 6
    enrich_top_factions: int = 4
    enrich_strict: bool = False
    enrich_force: bool = False
