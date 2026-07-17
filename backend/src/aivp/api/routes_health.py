from typing import Any

from fastapi import APIRouter, Depends, Request

from aivp.api.deps import get_settings
from aivp.config import Settings
from aivp.llm.deepseek_client import DeepSeekClient
from aivp.llm.ollama_client import OllamaClient

router = APIRouter(tags=["health"])


@router.get("/health/ollama")
def health_ollama(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    return {"ok": client.healthy(), "base_url": settings.ollama_base_url, "model": settings.ollama_model}


@router.get("/health/ollama-vision")
def health_ollama_vision(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from aivp.llm.ollama_vision_client import OllamaVisionClient

    client = OllamaVisionClient(settings.ollama_base_url, settings.ollama_vision_model)
    return {
        "ok": client.healthy(),
        "model_available": client.model_available(),
        "base_url": settings.ollama_base_url,
        "model": settings.ollama_vision_model,
    }


@router.get("/health/comfy")
def health_comfy(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from aivp.visual.image_backend import ComfyImageBackend, StubImageBackend

    if (settings.image_backend or "").lower() == "comfy":
        client = ComfyImageBackend(settings.comfy_base_url, settings.comfy_checkpoint)
        return {
            "ok": client.healthy(),
            "backend": "comfy",
            "base_url": settings.comfy_base_url,
            "checkpoint": settings.comfy_checkpoint,
        }
    stub = StubImageBackend()
    return {
        "ok": stub.healthy(),
        "backend": "stub",
        "base_url": settings.comfy_base_url,
        "checkpoint": settings.comfy_checkpoint,
        "note": "Using stub images until AIVP_IMAGE_BACKEND=comfy and ComfyUI is running",
    }


@router.get("/health/deepseek")
def health_deepseek(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    configured = bool(settings.deepseek_api_key)
    client = getattr(request.app.state, "shot_llm", None)
    if client is None and configured:
        client = DeepSeekClient(
            settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    ok = bool(client.healthy()) if client is not None else False
    return {
        "ok": ok,
        "configured": configured,
        "base_url": settings.deepseek_base_url,
        "model": settings.deepseek_model,
    }
