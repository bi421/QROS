"""HTTP request context and tracing middleware."""
from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from researchos.saas.observability import log_request, request_id_var, tracer

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = supplied[:MAX_REQUEST_ID_LENGTH] if supplied else str(uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = perf_counter()
        with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
            try:
                response = await call_next(request)
            finally:
                duration_ms = (perf_counter() - started) * 1000.0
                log_request(
                    level="info",
                    message="http_request",
                    duration_ms=duration_ms,
                    method=request.method,
                    path=request.url.path,
                )
                request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["MAX_REQUEST_ID_LENGTH", "REQUEST_ID_HEADER", "RequestContextMiddleware"]
