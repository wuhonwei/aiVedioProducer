from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

import httpx

from aivp.jobs.control import JobCancelled


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        if should_cancel is None:
            return self._post_json(payload)

        # Run the HTTP call in a side thread so cancel can interrupt waiting.
        box: dict[str, Any] = {}

        def _worker() -> None:
            try:
                box["value"] = self._post_json(payload)
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True, name="ollama-call")
        thread.start()
        while thread.is_alive():
            if should_cancel():
                raise JobCancelled("ollama_interrupted")
            thread.join(0.4)
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            content = r.json()["message"]["content"]
        return json.loads(content)

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except httpx.HTTPError:
            return False
