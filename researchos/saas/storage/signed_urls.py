"""Tenant-bound application signatures for private object access."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote
from uuid import UUID

DEFAULT_EXPIRY_SECONDS = 3600


def _payload(tenant_id: UUID, path: str, expires_at: int) -> bytes:
    return f"{tenant_id}:{expires_at}:{path}".encode("utf-8")


def generate_signed_url(
    *,
    tenant_id: UUID,
    path: str,
    secret: str,
    base_url: str = "/v1/storage/object",
    expires_in: int = DEFAULT_EXPIRY_SECONDS,
) -> str:
    if expires_in < 1 or expires_in > DEFAULT_EXPIRY_SECONDS:
        raise ValueError("invalid expiry")
    if not path.startswith(f"tenant/{tenant_id}/"):
        raise PermissionError("object path is outside tenant boundary")
    expires_at = int(time.time()) + expires_in
    signature = hmac.new(
        secret.encode("utf-8"),
        _payload(tenant_id, path, expires_at),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{base_url}?tenant_id={quote(str(tenant_id))}&expires={expires_at}&path={quote(path, safe='')}&signature={quote(encoded)}"


def verify_signed_url(
    *,
    tenant_id: UUID,
    path: str,
    expires_at: int,
    signature: str,
    secret: str,
    now: int | None = None,
) -> bool:
    if not path.startswith(f"tenant/{tenant_id}/"):
        return False
    current = int(time.time()) if now is None else now
    if expires_at < current:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        _payload(tenant_id, path, expires_at),
        hashlib.sha256,
    ).digest()
    supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    return hmac.compare_digest(expected, supplied)


__all__ = ["DEFAULT_EXPIRY_SECONDS", "generate_signed_url", "verify_signed_url"]
