from typing import Any, Protocol


class LlmClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict[str, Any]: ...
