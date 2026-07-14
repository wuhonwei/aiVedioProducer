from __future__ import annotations

import threading


class JobCancelled(Exception):
    """Raised when a running pipeline job is cancelled by the user."""


class JobControl:
    """In-process cancel flags for background pipeline jobs."""

    def __init__(self) -> None:
        self._flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def register(self, job_id: str) -> threading.Event:
        with self._lock:
            event = threading.Event()
            self._flags[job_id] = event
            return event

    def has_worker(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._flags

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            event = self._flags.get(job_id)
            if event is None:
                return False
            event.set()
            return True

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._flags.get(job_id)
            return bool(event is not None and event.is_set())

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._flags.pop(job_id, None)
