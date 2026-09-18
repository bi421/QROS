"""Rate limiting primitives for QROS SaaS."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time
from typing import Any, Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool:
        ...


@dataclass
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Development/test-only in-process rate limiter."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= self.window_seconds:
                self._windows[key] = _Window(now, 1)
                return True
            if window.count >= self.limit:
                return False
            window.count += 1
            return True


class SupabaseRateLimiter:
    """Shared fixed-window limiter backed by the server-only Postgres RPC."""

    def __init__(self, supabase_client: Any, *, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")
        self._client = supabase_client
        self.limit = limit
        self.window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        result = self._client.rpc(
            "consume_api_rate_limit",
            {
                "p_rate_key": key,
                "p_limit": self.limit,
                "p_window_seconds": self.window_seconds,
            },
        ).execute()
        return bool(result.data)
