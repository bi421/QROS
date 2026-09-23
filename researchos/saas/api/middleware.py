"""Canonical HTTP request context middleware for the SaaS API."""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from opentelemetry import trace

_TRACER = trace.get_tracer("qros.saas")

from researchos.saas.observability import StructuredRequestObserver, observe_request
from researchos.saas.request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generate/propagate request IDs, tracing context, and structured request events."""

    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = supplied[:MAX_REQUEST_ID_LENGTH] if supplied else str(uuid4())
        request_id = "".join(
            char if 32 <= ord(char) != 127 else "-" for char in request_id
        )
        request.state.request_id = request_id
        request.state.correlation_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        observer = getattr(request.app.state, "observability", None)
        with _TRACER.start_as_current_span(f"{request.method} {request.url.path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            try:
                response = await call_next(request)
            except Exception as exc:
                if isinstance(observer, StructuredRequestObserver):
                observe_request(
                    observer,
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    started_at=started,
                )
                span.record_exception(exc)
                reset_request_id(token)
                raise
        response.headers[REQUEST_ID_HEADER] = request_id
        if isinstance(observer, StructuredRequestObserver):
            observe_request(
                observer,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                started_at=started,
            )
        reset_request_id(token)
        return response


__all__ = ["MAX_REQUEST_ID_LENGTH", "REQUEST_ID_HEADER", "RequestContextMiddleware"]
