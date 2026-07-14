from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from typing import Any

import httpx

from aivp.jobs.control import JobCancelled


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


class DeepSeekClient:
    """OpenAI-compatible DeepSeek Chat Completions client."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout: float = 180.0,
    ):
        self.api_key = api_key
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
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
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

        thread = threading.Thread(target=_worker, daemon=True, name="deepseek-call")
        thread.start()
        while thread.is_alive():
            if should_cancel():
                raise JobCancelled("deepseek_interrupted")
            thread.join(0.4)
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            raise ValueError("deepseek_json_not_object")
        return parsed

    def healthy(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return r.status_code == 200
        except httpx.HTTPError:
            return False
