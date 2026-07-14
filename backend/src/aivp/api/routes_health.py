from typing import Any

from fastapi import APIRouter, Depends

from aivp.api.deps import get_settings
from aivp.config import Settings
from aivp.llm.ollama_client import OllamaClient

router = APIRouter(tags=["health"])


@router.get("/health/ollama")
def health_ollama(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    return {"ok": client.healthy(), "base_url": settings.ollama_base_url, "model": settings.ollama_model}
