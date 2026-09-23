"""Structured observability primitives for the SaaS boundary."""
from __future__ import annotations

import contextvars
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from opentelemetry import trace
from prometheus_client import Counter, Histogram

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)

jobs_created_total = Counter("jobs_created_total", "Research jobs created")
jobs_failed_total = Counter("jobs_failed_total", "Research jobs failed")
jobs_duration_seconds = Histogram("jobs_duration_seconds", "Research job duration")
tenant_isolation_violations_total = Counter("tenant_isolation_violations_total", "Tenant isolation violations")
rls_violations_total = Counter("rls_violations_total", "RLS violations")

tracer = trace.get_tracer("qros.saas")


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )


def get_logger() -> Any:
    return structlog.get_logger("qros.saas")


def log_request(*, level: str, message: str, duration_ms: float, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "request_id": request_id_var.get(),
        "tenant_id": tenant_id_var.get(),
        "job_id": job_id_var.get(),
        "message": message,
        "duration_ms": duration_ms,
        **fields,
    }
    get_logger().info(message, **{k: v for k, v in payload.items() if k != "message"})


def metrics_text() -> str:
    from prometheus_client import generate_latest
    return generate_latest().decode("utf-8")


def parse_json_log(line: str) -> dict[str, Any]:
    return json.loads(line)
