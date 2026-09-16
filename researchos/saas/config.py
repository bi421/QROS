"""Validated runtime configuration for the ResearchOS SaaS boundary.

Configuration is environment-driven and deliberately contains no scientific
parameters. Production deployments must fail closed when security-critical
settings are absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when runtime configuration is invalid or incomplete."""


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigurationError(f"invalid boolean value for {name}: {raw!r}")


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"invalid integer value for {name}: {raw!r}") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class SaaSSettings:
    """Immutable application settings shared by API and worker processes."""

    environment: str
    service_name: str
    log_level: str
    auth_required: bool
    request_timeout_seconds: int
    max_request_body_bytes: int
    request_id_max_length: int
    rate_limit_per_minute: int
    supabase_url: str | None
    supabase_publishable_key: str | None
    supabase_service_role_key: str | None

    @classmethod
    def from_env(cls) -> "SaaSSettings":
        environment = os.getenv("RESEARCHOS_ENV", "development").strip().lower()
        if environment not in {"development", "test", "staging", "production"}:
            raise ConfigurationError(f"unsupported RESEARCHOS_ENV: {environment!r}")

        auth_required = _bool("RESEARCHOS_AUTH_REQUIRED", environment == "production")
        supabase_url = os.getenv("SUPABASE_URL", "").strip() or None
        publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip() or None
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or None

        if environment == "production" and auth_required:
            if not supabase_url:
                raise ConfigurationError("SUPABASE_URL is required in production")
            if not service_role_key:
                raise ConfigurationError("SUPABASE_SERVICE_ROLE_KEY is required in production")

        return cls(
            environment=environment,
            service_name=os.getenv("RESEARCHOS_SERVICE_NAME", "researchos-saas").strip()
            or "researchos-saas",
            log_level=os.getenv("RESEARCHOS_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            auth_required=auth_required,
            request_timeout_seconds=_positive_int("RESEARCHOS_REQUEST_TIMEOUT_SECONDS", 60),
            max_request_body_bytes=_positive_int(
                "RESEARCHOS_MAX_REQUEST_BODY_BYTES", 10_000_000
            ),
            request_id_max_length=_positive_int("RESEARCHOS_REQUEST_ID_MAX_LENGTH", 128),
            rate_limit_per_minute=_positive_int("RESEARCHOS_RATE_LIMIT_PER_MINUTE", 60),
            supabase_url=supabase_url,
            supabase_publishable_key=publishable_key,
            supabase_service_role_key=service_role_key,
        )


__all__ = ["ConfigurationError", "SaaSSettings"]
