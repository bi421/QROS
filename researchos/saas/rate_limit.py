"""Rate limiting primitives for QROS SaaS."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time
from typing import Any, Protocol
from researchos.saas.contracts import Plan


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool:
        ...

    def retry_after(self, key: str) -> int:
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

    def retry_after(self, key: str) -> int:
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                return 0
            remaining = self.window_seconds - (time.monotonic() - window.started_at)
            return max(1, int(remaining + 0.999))

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


class PlanRateLimiter:
    """Workspace-scoped fixed windows with billing-plan quotas."""

    LIMITS = {Plan.FREE: 100, Plan.PRO: 1000, Plan.TEAM: 1000, Plan.ENTERPRISE: 1000}

    def __init__(self, *, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._limiters = {
            plan: FixedWindowRateLimiter(limit=limit, window_seconds=window_seconds)
            for plan, limit in self.LIMITS.items()
        }

    def allow(self, workspace_id: str, plan: Plan) -> bool:
        return self._limiters[plan].allow(workspace_id)

    def retry_after(self, workspace_id: str, plan: Plan) -> int:
        return self._limiters[plan].retry_after(workspace_id)

