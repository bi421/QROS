"""OpenTelemetry tracing primitives with request/job span propagation."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace

_tracer = trace.get_tracer("qros.saas")


@contextmanager
def api_span(request_id: str) -> Iterator[trace.Span]:
    with _tracer.start_as_current_span("qros.api", attributes={"qros.request_id": request_id}) as span:
        yield span


@contextmanager
def job_span(request_id: str, job_id: str) -> Iterator[trace.Span]:
    with _tracer.start_as_current_span(
        "qros.job",
        attributes={"qros.request_id": request_id, "qros.job_id": job_id},
    ) as span:
        yield span


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")
