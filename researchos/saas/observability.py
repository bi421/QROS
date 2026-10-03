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
import threading
import time
from typing import Mapping

try:
    import structlog
    import structlog.stdlib
except ImportError:  # pragma: no cover
    structlog = None

_LOGGER = structlog.get_logger("qros.saas") if structlog is not None else None

if structlog is not None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

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
    jobs_created_total: int = 0
    jobs_failed_total: int = 0
    jobs_duration_seconds_sum: float = 0.0
    jobs_duration_seconds_count: int = 0
    tenant_isolation_violations_total: int = 0
    rls_violations_total: int = 0
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

    def job_created(self) -> None:
        with self._lock:
            self.jobs_created_total += 1

    def job_finished(self, duration_seconds: float, failed: bool) -> None:
        with self._lock:
            self.jobs_duration_seconds_sum += duration_seconds
            self.jobs_duration_seconds_count += 1
            if failed:
                self.jobs_failed_total += 1

    def prometheus_text(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP jobs_created_total Jobs created.",
            "# TYPE jobs_created_total counter",
            "jobs_created_total " + str(snapshot["jobs_created_total"]),
            "# HELP jobs_failed_total Jobs failed.",
            "# TYPE jobs_failed_total counter",
            "jobs_failed_total " + str(snapshot["jobs_failed_total"]),
            "# HELP jobs_duration_seconds Job execution duration.",
            "# TYPE jobs_duration_seconds summary",
            "jobs_duration_seconds_sum " + f'{snapshot["jobs_duration_seconds_sum"]:.6f}',
            "jobs_duration_seconds_count " + str(snapshot["jobs_duration_seconds_count"]),
            "# HELP tenant_isolation_violations_total Tenant isolation violations.",
            "# TYPE tenant_isolation_violations_total counter",
            "tenant_isolation_violations_total " + str(snapshot["tenant_isolation_violations_total"]),
            "# HELP rls_violations_total RLS violations.",
            "# TYPE rls_violations_total counter",
            "rls_violations_total " + str(snapshot["rls_violations_total"]),
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


DEFAULT_METRICS = RequestMetrics()


class StructuredRequestObserver:
    """Record and emit one sanitized event for each completed HTTP request."""

    def __init__(self, metrics: RequestMetrics | None = None) -> None:
        self.metrics = metrics or DEFAULT_METRICS

    def observe(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        tenant_id: object | None = None,
        job_id: object | None = None,
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
        event["timestamp"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        event["level"] = "info"
        event["tenant_id"] = str(tenant_id) if tenant_id is not None else None
        event["job_id"] = str(job_id) if job_id is not None else None
        if _LOGGER is not None:
            _LOGGER.info("request_completed", **event)
        if status_code >= 500:
            error_event = {
                "event": "http_request_error",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
            }
            if _LOGGER is not None:
                _LOGGER.error("request_error", **sanitize_log_fields(error_event))


def observe_request(
    observer: StructuredRequestObserver,
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    started_at: float,
    tenant_id: object | None = None,
    job_id: object | None = None,
) -> None:
    observer.observe(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
        tenant_id=tenant_id,
        job_id=job_id,
    )


def metrics_registry() -> RequestMetrics:
    return DEFAULT_METRICS
