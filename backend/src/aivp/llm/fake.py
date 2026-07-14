from collections.abc import Callable
from typing import Any


class FakeLlm:
    def __init__(
        self,
        script: dict[str, dict[str, Any]] | None = None,
        default: dict[str, Any] | None = None,
    ):
        self.script = script or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if should_cancel and should_cancel():
            from aivp.jobs.control import JobCancelled

            raise JobCancelled("fake_llm")
        self.calls.append((system, user))
        if user in self.script:
            return self.script[user]
        if self.default is not None:
            return self.default
        raise KeyError(f"no_fake_response_for:{user[:80]}")
