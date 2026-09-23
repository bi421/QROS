"""HTTP request middleware and context propagation for SaaS observability."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from researchos.saas.auth.permissions import reset_request_id, set_request_id
from researchos.saas.observability import (
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
        request_id = "".join(char if 32 <= ord(char) != 127 else "-" for char in request_id)

        request.state.request_id = request_id
        request.state.correlation_id = request_id

        request_id_token = request_id_var.set(request_id)
        permission_token = set_request_id(request_id)
        started = time.perf_counter()

        response: Response | None = None
        status_code = 500

        try:
            with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                finally:
                    duration_ms = (time.perf_counter() - started) * 1000.0

                    observe_request(
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        tenant_id=getattr(
                            getattr(request.state, "tenant", None),
                            "workspace_id",
                            None,
                        ),
                        job_id=getattr(request.state, "job_id", None),
                    )

                    log_request(
                        level="info",
                        message="http_request",
                        duration_ms=duration_ms,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        request_id=request_id,
                        tenant_id=getattr(
                            getattr(request.state, "tenant", None),
                            "workspace_id",
                            None,
                        ),
                        job_id=getattr(request.state, "job_id", None),
                    )
        finally:
            request_id_var.reset(request_id_token)
            reset_request_id(permission_token)

        if response is None:
            raise RuntimeError("request middleware completed without a response")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["MAX_REQUEST_ID_LENGTH", "REQUEST_ID_HEADER", "RequestContextMiddleware"]
