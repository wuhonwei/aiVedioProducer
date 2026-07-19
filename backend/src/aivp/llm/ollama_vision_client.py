from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from aivp.jobs.control import JobCancelled


def _strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
    return text


class OllamaVisionClient:
    """Ollama multimodal chat (e.g. qwen2.5vl) with JSON responses."""

    def __init__(self, base_url: str, model: str, timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete_json_with_image(
        self,
        system: str,
        user: str,
        image_path: Path,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        raw = Path(image_path).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user,
                    "images": [b64],
                },
            ],
        }
        if should_cancel is None:
            return self._post_json(payload)

        box: dict[str, Any] = {}

        def _worker() -> None:
            try:
                box["value"] = self._post_json(payload)
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True, name="ollama-vision")
        thread.start()
        while thread.is_alive():
            if should_cancel():
                raise JobCancelled("ollama_vision_interrupted")
            thread.join(0.4)
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            content = r.json()["message"]["content"]
        try:
            data = json.loads(_strip_json_fences(content))
        except json.JSONDecodeError as exc:
            raise ValueError(f"ollama_vision_invalid_json:{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("ollama_vision_json_not_object")
        return data

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/api/tags")
                if r.status_code != 200:
                    return False
                names = {
                    str(m.get("name") or "")
                    for m in (r.json().get("models") or [])
                    if isinstance(m, dict)
                }
                # Exact or prefix match (tags like qwen2.5vl:7b).
                return self.model in names or any(n.startswith(self.model.split(":")[0]) for n in names if "vl" in n or "llava" in n or "vision" in n)
        except httpx.HTTPError:
            return False

    def model_available(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/api/tags")
                if r.status_code != 200:
                    return False
                names = {str(m.get("name") or "") for m in (r.json().get("models") or [])}
                return self.model in names
        except httpx.HTTPError:
            return False
