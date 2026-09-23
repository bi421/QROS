"""Structured application observability for the QROS SaaS boundary.

Logs are emitted as JSON records with a stable correlation schema.  Metrics are
process-local Prometheus counters and OpenTelemetry spans are created without
requiring an exporter in unit tests.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Iterator, Mapping
from uuid import UUID

from opentelemetry import trace

_LOGGER = logging.getLogger("qros.saas")
_TRACER = trace.get_tracer("qros.saas")

request_id_context: ContextVar[str | None] = ContextVar("qros_request_id", default=None)
tenant_id_context: ContextVar[str | None] = ContextVar("qros_tenant_id", default=None)
job_id_context: ContextVar[str | None] = ContextVar("qros_job_id", default=None)

_SENSITIVE_KEYS = frozenset({
    "authorization", "cookie", "set-cookie", "x-api-key", "api-key", "token",
    "access-token", "refresh-token", "password", "secret", "signature",
    "billing-signature", "metrics-token",
})
_LATENCY_BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000)


def _id(value: UUID | str | None) -> str | None:
    return str(value) if value is not None else None


def sanitize_log_fields(fields: Mapping[str, object]) -> dict[str, object]:
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
    """Thread-safe application metrics."""

    requests_total: int = 0
    errors_total: int = 0
    jobs_created_total: int = 0
    jobs_failed_total: int = 0
    tenant_isolation_violations_total: int = 0
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

    def inc_job_created(self) -> None:
        with self._lock:
            self.jobs_created_total += 1

    def inc_job_failed(self) -> None:
        with self._lock:
            self.jobs_failed_total += 1

    def inc_tenant_isolation_violation(self) -> None:
        with self._lock:
            self.tenant_isolation_violations_total += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "jobs_created_total": self.jobs_created_total,
                "jobs_failed_total": self.jobs_failed_total,
                "tenant_isolation_violations_total": self.tenant_isolation_violations_total,
                "status_counts": dict(self.status_counts),
                "latency_buckets": dict(self.latency_buckets),
                "latency_sum_ms": self.latency_sum_ms,
            }

    def prometheus_text(self) -> str:
        s = self.snapshot()
        lines = [
            "# HELP jobs_created_total Research jobs accepted for execution.",
            "# TYPE jobs_created_total counter",
            f"jobs_created_total {s['jobs_created_total']}",
            "# HELP jobs_failed_total Research jobs that reached a failed state.",
            "# TYPE jobs_failed_total counter",
            f"jobs_failed_total {s['jobs_failed_total']}",
            "# HELP tenant_isolation_violations_total Detected tenant isolation violations.",
            "# TYPE tenant_isolation_violations_total counter",
            f"tenant_isolation_violations_total {s['tenant_isolation_violations_total']}",
            "# HELP qros_http_requests_total Total HTTP requests observed.",
            "# TYPE qros_http_requests_total counter",
            f"qros_http_requests_total {s['requests_total']}",
            "# HELP qros_http_errors_total Total HTTP 5xx responses observed.",
            "# TYPE qros_http_errors_total counter",
            f"qros_http_errors_total {s['errors_total']}",
            "# HELP qros_http_request_duration_ms HTTP request duration in milliseconds.",
            "# TYPE qros_http_request_duration_ms histogram",
        ]
        buckets = s["latency_buckets"]
        assert isinstance(buckets, dict)
        for bucket in _LATENCY_BUCKETS_MS:
            lines.append(
                f'qros_http_request_duration_ms_bucket{{le="{bucket}"}} {int(buckets.get(bucket, 0))}'
            )
        lines.extend([
            f'qros_http_request_duration_ms_bucket{{le="+Inf"}} {int(s["requests_total"])}',
            f"qros_http_request_duration_ms_sum {float(s['latency_sum_ms']):.3f}",
            f"qros_http_request_duration_ms_count {int(s['requests_total'])}",
            "",
        ])
        return "\n".join(lines)


@dataclass
class ObservabilityContext:
    request_id: str | None = None
    tenant_id: UUID | str | None = None
    job_id: UUID | str | None = None

    def bind(self) -> tuple[object, object, object]:
        return (
            request_id_context.set(self.request_id),
            tenant_id_context.set(_id(self.tenant_id)),
            job_id_context.set(_id(self.job_id)),
        )


def reset_context(tokens: tuple[object, object, object]) -> None:
    request_id_context.reset(tokens[0])
    tenant_id_context.reset(tokens[1])
    job_id_context.reset(tokens[2])


def emit_log(
    *,
    level: int,
    message: str,
    duration_ms: float = 0.0,
    request_id: str | None = None,
    tenant_id: UUID | str | None = None,
    job_id: UUID | str | None = None,
) -> None:
    """Emit one JSON-parseable log record with the mandatory correlation schema."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level),
        "request_id": request_id if request_id is not None else request_id_context.get(),
        "tenant_id": _id(tenant_id) if tenant_id is not None else tenant_id_context.get(),
        "job_id": _id(job_id) if job_id is not None else job_id_context.get(),
        "message": message,
        "duration_ms": round(max(0.0, duration_ms), 3),
    }
    _LOGGER.log(level, json.dumps(event, sort_keys=True, separators=(",", ":")))


@contextmanager
def span(name: str, **attributes: object) -> Iterator[object]:
    """Create an OpenTelemetry span and annotate it with safe correlation data."""
    with _TRACER.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))
        yield current


class StructuredRequestObserver:
    def __init__(self, metrics: RequestMetrics | None = None) -> None:
        self.metrics = metrics or RequestMetrics()

    def observe(
        self, *, request_id: str, method: str, path: str, status_code: int,
        duration_ms: float, tenant_id: UUID | str | None = None,
        job_id: UUID | str | None = None,
    ) -> None:
        self.metrics.observe(status_code, duration_ms)
        emit_log(
            level=logging.ERROR if status_code >= 500 else logging.INFO,
            message=f"http {method} {path} -> {status_code}",
            request_id=request_id,
            tenant_id=tenant_id,
            job_id=job_id,
            duration_ms=duration_ms,
        )


def observe_request(
    observer: StructuredRequestObserver, *, request_id: str, method: str,
    path: str, status_code: int, started_at: float,
    tenant_id: UUID | str | None = None, job_id: UUID | str | None = None,
) -> None:
    observer.observe(
        request_id=request_id, method=method, path=path, status_code=status_code,
        duration_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
        tenant_id=tenant_id, job_id=job_id,
    )
