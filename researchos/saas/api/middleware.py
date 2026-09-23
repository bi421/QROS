"""HTTP request middleware and context propagation for SaaS observability."""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from researchos.saas.auth.permissions import reset_request_id, set_request_id
from researchos.saas.observability import observe_request

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Create/propagate request context and emit one structured completion event."""

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
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            observe_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                tenant_id=getattr(getattr(request.state, "tenant", None), "workspace_id", None),
            )
            raise
        finally:
            reset_request_id(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        observe_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            tenant_id=getattr(getattr(request.state, "tenant", None), "workspace_id", None),
            job_id=getattr(request.state, "job_id", None),
        )
        return response


__all__ = ["REQUEST_ID_HEADER", "RequestContextMiddleware"]
