from aivp.config import Settings


def test_default_settings():
    s = Settings(data_root="/tmp/aivp-data")
    assert s.ollama_base_url == "http://127.0.0.1:11434"
    assert s.ollama_model == "qwen2.5:14b"
    assert s.chunk_size == 1200
    assert s.chunk_overlap == 150
