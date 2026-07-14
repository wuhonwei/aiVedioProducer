from collections.abc import Callable
from typing import Any, Protocol


class LlmClient(Protocol):
    def complete_json(
        self,
        system: str,
        user: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]: ...
