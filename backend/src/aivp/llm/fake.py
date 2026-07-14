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

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        if user in self.script:
            return self.script[user]
        if self.default is not None:
            return self.default
        raise KeyError(f"no_fake_response_for:{user[:80]}")
