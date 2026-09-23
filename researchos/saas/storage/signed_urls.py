"""Tenant-bound application signatures for private Supabase Storage URLs."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID
import posixpath
import re

DEFAULT_EXPIRY_SECONDS = 3600


class SignedUrlError(ValueError):
    pass


def _secret() -> bytes:
    value = os.environ.get("QROS_STORAGE_SIGNING_SECRET")
    if not value:
        raise SignedUrlError("QROS_STORAGE_SIGNING_SECRET is not configured")
    return value.encode("utf-8")


def _signature(tenant_id: UUID, storage_path: str, expires_at: int) -> str:
    message = f"{tenant_id}:{storage_path}:{expires_at}".encode("utf-8")
    digest = hmac.new(_secret(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _validate_storage_path(storage_path: str, tenant_id: UUID) -> None:
    expected = re.compile(rf"^tenant/{re.escape(str(tenant_id))}/datasets/[0-9a-f]{{64}}/[1-9][0-9]*$")
    normalized = posixpath.normpath(storage_path)
    if normalized != storage_path or ".." in storage_path.split("/") or not expected.fullmatch(storage_path):
        raise SignedUrlError("INVALID_PATH")


def bind_signed_url(provider_url: str, tenant_id: UUID, storage_path: str, *, expires_in: int = DEFAULT_EXPIRY_SECONDS, now: int | None = None) -> str:
    _validate_storage_path(storage_path, tenant_id)
    if expires_in != DEFAULT_EXPIRY_SECONDS:
        raise SignedUrlError("storage signed URL expiry must be exactly 3600 seconds")
    issued = int(time.time()) if now is None else now
    expires_at = issued + expires_in
    parts = urlsplit(provider_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"tenant_id": str(tenant_id), "expires": str(expires_at), "sig": _signature(tenant_id, storage_path, expires_at)})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def verify_signed_url(url: str, tenant_id: UUID, storage_path: str, *, now: int | None = None) -> bool:
    _validate_storage_path(storage_path, tenant_id)
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    try:
        expires_at = int(params["expires"])
        supplied_tenant = UUID(params["tenant_id"])
        supplied_sig = params["sig"]
    except (KeyError, ValueError):
        return False
    if supplied_tenant != tenant_id:
        return False
    current = int(time.time()) if now is None else now
    if expires_at < current:
        return False
    expected = _signature(tenant_id, storage_path, expires_at)
    return hmac.compare_digest(supplied_sig, expected)


__all__ = ["DEFAULT_EXPIRY_SECONDS", "SignedUrlError", "bind_signed_url", "verify_signed_url"]
