"""Production-safe observability primitives for the QROS SaaS boundary.

The module deliberately has no third-party dependency.  It provides:
- structured JSON request events;
- bounded, process-local request counters and latency buckets;
- Prometheus text exposition for an internal scrape surface;
- strict field sanitization so credentials and request payloads are never emitted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import logging
import threading
import time
from typing import Mapping

_LOGGER = logging.getLogger("qros.saas")

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "token",
        "access-token",
        "refresh-token",
        "password",
        "secret",
        "signature",
        "billing-signature",
    "metrics-token",
    }
)

_LATENCY_BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000)


def sanitize_log_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Return a shallow, allow-by-name sanitized mapping for structured logs."""
    sanitized: dict[str, object] = {}
    for key, value in fields.items():
        normalized = key.lower().replace("_", "-")
        if normalized in _SENSITIVE_KEYS or any(
            marker in normalized for marker in ("password", "secret", "token", "credential")
        ):
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


@dataclass
class RequestMetrics:
    """Thread-safe request metrics with bounded cardinality."""

    requests_total: int = 0
    errors_total: int = 0
    status_counts: Counter[int] = field(default_factory=Counter)
    latency_buckets: Counter[int] = field(default_factory=Counter)
    latency_sum_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def observe(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self.requests_total += 1
            if status_code >= 500:
                self.errors_total += 1
            self.status_counts[status_code] += 1
            for bucket in _LATENCY_BUCKETS_MS:
                if duration_ms <= bucket:
                    self.latency_buckets[bucket] += 1
            self.latency_buckets[0] += 1
            self.latency_sum_ms += duration_ms

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "status_counts": dict(self.status_counts),
                "latency_buckets": dict(self.latency_buckets),
                "latency_sum_ms": self.latency_sum_ms,
            }

    def prometheus_text(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP qros_http_requests_total Total HTTP requests observed.",
            "# TYPE qros_http_requests_total counter",
            f"qros_http_requests_total {snapshot['requests_total']}",
            "# HELP qros_http_errors_total Total HTTP 5xx responses observed.",
            "# TYPE qros_http_errors_total counter",
            f"qros_http_errors_total {snapshot['errors_total']}",
            "# HELP qros_http_request_duration_ms HTTP request duration in milliseconds.",
            "# TYPE qros_http_request_duration_ms histogram",
        ]
        cumulative = 0
        buckets = snapshot["latency_buckets"]
        assert isinstance(buckets, dict)
        for bucket in _LATENCY_BUCKETS_MS:
            cumulative = int(buckets.get(bucket, 0))
            lines.append(
                f'qros_http_request_duration_ms_bucket{{le="{bucket}"}} {cumulative}'
            )
        total = int(snapshot["requests_total"])
        lines.extend(
            [
                f'qros_http_request_duration_ms_bucket{{le="+Inf"}} {total}',
                f"qros_http_request_duration_ms_sum {snapshot['latency_sum_ms']:.3f}",
                f"qros_http_request_duration_ms_count {total}",
                "",
            ]
        )
        return "\n".join(lines)


class StructuredRequestObserver:
    """Record and emit one sanitized event for each completed HTTP request."""

    def __init__(self, metrics: RequestMetrics | None = None) -> None:
        self.metrics = metrics or RequestMetrics()

    def observe(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        self.metrics.observe(status_code, duration_ms)
        event = sanitize_log_fields(
            {
                "event": "http_request_completed",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
            }
        )
        _LOGGER.info(json.dumps(event, sort_keys=True, separators=(",", ":")))


def observe_request(
    observer: StructuredRequestObserver,
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    started_at: float,
) -> None:
    observer.observe(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
    )
