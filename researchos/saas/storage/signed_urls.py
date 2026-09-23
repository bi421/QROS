"""Tenant-bound signed URL helpers for QROS object storage."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class SignedObject:
    tenant_id: str
    path: str
    expires_at: int
    signature: str


def dataset_object_path(tenant_id: str, content_sha256: str, version: int) -> str:
    """Canonical immutable dataset path."""
    tenant = str(tenant_id).strip()
    digest = content_sha256.strip().lower()
    if not tenant or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid tenant or SHA-256")
    if version < 1:
        raise ValueError("version must be positive")
    return f"tenant/{tenant}/datasets/{digest}/{version}/"


def sign_path(tenant_id: str, path: str, secret: str, *, expires_in: int = 3600, now: int | None = None) -> str:
    if not 1 <= expires_in <= 3600:
        raise ValueError("signed URL expiry must be between 1 and 3600 seconds")
    if not path.startswith(f"tenant/{tenant_id}/"):
        raise PermissionError("object path does not belong to tenant")
    issued = int(time.time() if now is None else now)
    expires_at = issued + expires_in
    payload = f"{tenant_id}:{path}:{expires_at}".encode()
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"{path}?tenant_id={quote(tenant_id)}&expires={expires_at}&sig={signature}"


def verify_path_signature(
    tenant_id: str,
    path: str,
    expires_at: int,
    signature: str,
    secret: str,
    *,
    now: int | None = None,
) -> bool:
    if not path.startswith(f"tenant/{tenant_id}/"):
        return False
    if expires_at < int(time.time() if now is None else now):
        return False
    payload = f"{tenant_id}:{path}:{expires_at}".encode()
    expected = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    ).decode().rstrip("=")
    return hmac.compare_digest(expected, signature)


__all__ = ["SignedObject", "dataset_object_path", "sign_path", "verify_path_signature"]
