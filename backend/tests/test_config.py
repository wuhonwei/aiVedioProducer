from aivp.config import Settings


def test_default_settings():
    # Ignore repo .env so local overrides don't break defaults.
    s = Settings(data_root="/tmp/aivp-data", _env_file=None)
    assert s.ollama_base_url == "http://127.0.0.1:11434"
    assert s.ollama_model == "qwen2.5:14b"
    assert s.chunk_size == 1200
    assert s.chunk_overlap == 150
    assert s.image_backend == "stub"
