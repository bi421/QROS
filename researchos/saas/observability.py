"""Production-safe observability primitives for the QROS SaaS boundary.

The module provides:
- sanitized structured JSON request events;
- context-local request, tenant, actor, and job correlation;
- bounded process-local HTTP request metrics;
- Prometheus exposition;
- OpenTelemetry tracing;
- structlog-based application logging;
- job and security observability counters.
"""

from __future__ import annotations

import contextvars
from collections import Counter
from dataclasses import dataclass, field
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Mapping

import structlog
from opentelemetry import trace
from prometheus_client import Counter as PrometheusCounter
from prometheus_client import Histogram
from prometheus_client import generate_latest

_LOGGER = logging.getLogger("qros.saas")

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "token",
        "jwt",
        "access-token",
        "refresh-token",
        "password",
        "secret",
        "signature",
        "billing-signature",
        "metrics-token",
        "database-url",
        "database-url-credentials",
        "aws-access-key-id",
        "aws-secret-access-key",
        "private-dataset",
        "private-dataset-content",
        "dataset-content",
        "request-body",
        "raw-payload",
    }
)
_SENSITIVE_MARKERS = ("password", "secret", "token", "credential")
_SAFE_ERROR_METADATA_KEYS = frozenset(
    {
        "method",
        "path",
        "status_code",
        "resource_type",
        "resource_id",
    }
)

_LATENCY_BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000)

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_id",
    default=None,
)
actor_user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "actor_user_id",
    default=None,
)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "job_id",
    default=None,
)

jobs_created_total = PrometheusCounter(
    "jobs_created_total",
    "Research jobs created",
)
jobs_failed_total = PrometheusCounter(
    "jobs_failed_total",
    "Research jobs failed",
)
jobs_duration_seconds = Histogram(
    "jobs_duration_seconds",
    "Research job duration",
)
tenant_isolation_violations_total = PrometheusCounter(
    "tenant_isolation_violations_total",
    "Tenant isolation violations",
)
rls_violations_total = PrometheusCounter(
    "rls_violations_total",
    "RLS violations",
)

tracer = trace.get_tracer("qros.saas")


def sanitize_log_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Return a shallow, allow-by-name sanitized mapping for structured logs."""
    sanitized: dict[str, object] = {}

    for key, value in fields.items():
        normalized = key.lower().replace("_", "-")
        if normalized in _SENSITIVE_KEYS or any(
            marker in normalized for marker in _SENSITIVE_MARKERS
        ):
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value

    return sanitized


def _safe_error_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    """Keep error-event metadata to an explicit non-secret allowlist."""
    return sanitize_log_fields(
        {
            key: value
            for key, value in metadata.items()
            if key in _SAFE_ERROR_METADATA_KEYS
        }
    )


def observe_error(
    *,
    severity: str,
    error_code: str,
    error: BaseException,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Emit one stable, sanitized production error event."""
    payload: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "event": "qros_error",
        "service": "qros.saas",
        "request_id": request_id_var.get(),
        "tenant_id": tenant_id_var.get(),
        "actor_user_id": actor_user_id_var.get(),
        "research_job_id": job_id_var.get(),
        "error_class": type(error).__name__,
        "error_code": error_code,
    }
    if metadata:
        payload.update(_safe_error_metadata(metadata))

    sanitized = sanitize_log_fields(payload)
    rendered = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    if severity == "error":
        _LOGGER.error(rendered)
    else:
        _LOGGER.warning(rendered)


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
            "# HELP qros_http_errors_total Total 5xx responses observed.",
            "# TYPE qros_http_errors_total counter",
            f"qros_http_errors_total {snapshot['errors_total']}",
            "# HELP qros_http_request_duration_ms HTTP request duration in milliseconds.",
            "# TYPE qros_http_request_duration_ms histogram",
        ]
        buckets = snapshot["latency_buckets"]
        assert isinstance(buckets, dict)
        for bucket in _LATENCY_BUCKETS_MS:
            cumulative = int(buckets.get(bucket, 0))
            lines.append(f'qros_http_request_duration_ms_bucket{{le="{bucket}"}} {cumulative}')
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
        if status_code >= 500:
            error_event = sanitize_log_fields(
                {
                    "event": "http_request_error",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                }
            )
            _LOGGER.error(json.dumps(error_event, sort_keys=True, separators=(",", ":")))


def observe_request(
    observer: StructuredRequestObserver,
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    started_at: float,
) -> None:
    """Observe a request using a monotonic start timestamp."""
    observer.observe(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
    )


def configure_logging() -> None:
    """Configure structured JSON logging for the SaaS boundary."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )


def get_logger():
    """Return the QROS SaaS structured logger."""
    return structlog.get_logger("qros.saas")


def log_request(
    *,
    level: str,
    message: str,
    duration_ms: float,
    **fields: object,
) -> None:
    """Emit a sanitized structured request/application event."""
    payload = sanitize_log_fields(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "request_id": request_id_var.get(),
            "tenant_id": tenant_id_var.get(),
            "research_job_id": job_id_var.get(),
            "message": message,
            "duration_ms": duration_ms,
            **fields,
        }
    )
    get_logger().info(
        message,
        **{key: value for key, value in payload.items() if key != "message"},
    )


def metrics_text() -> str:
    """Return the process-wide Prometheus exposition payload."""
    return generate_latest().decode("utf-8")


def parse_json_log(line: str) -> dict[str, object]:
    """Parse a JSON log line into a dictionary."""
    return json.loads(line)
