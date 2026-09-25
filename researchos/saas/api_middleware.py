"""HTTP request context and tracing middleware."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from researchos.saas.observability import (
    StructuredRequestObserver,
    log_request,
    observe_request,
    request_id_var,
    tracer,
)

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Create request context, tracing, and structured completion telemetry."""

    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = supplied[:MAX_REQUEST_ID_LENGTH] if supplied else str(uuid4())
        request_id = "".join(
            char if 32 <= ord(char) != 127 else "-" for char in request_id
        )

        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = perf_counter()
        response: Response | None = None
        status_code = 500

        try:
            with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
                response = await call_next(request)
                status_code = response.status_code
        finally:
            duration_ms = (perf_counter() - started) * 1000.0
            observer = getattr(request.app.state, "observability", None)
            if isinstance(observer, StructuredRequestObserver) and request.url.path != "/metrics":
                observe_request(
                    observer,
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    started_at=started,
                )
            log_request(
                level="info",
                message="http_request",
                duration_ms=duration_ms,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                request_id=request_id,
            )
            request_id_var.reset(token)

        if response is None:
            raise RuntimeError("request middleware completed without a response")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["MAX_REQUEST_ID_LENGTH", "REQUEST_ID_HEADER", "RequestContextMiddleware"]
