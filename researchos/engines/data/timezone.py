"""Timezone normalization utilities for market data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimezoneResolutionError(ValueError):
    """Raised when a timezone name cannot be resolved."""


_COMMON_OFFSETS: Dict[str, int] = {
    "UTC": 0,
    "GMT": 0,
    "EST": -300,
    "EDT": -240,
    "CST": -360,
    "CDT": -300,
    "MST": -420,
    "MDT": -360,
    "PST": -480,
    "PDT": -420,
    "CET": 60,
    "CEST": 120,
    "EET": 120,
    "EEST": 180,
    "BST": 60,
    "IST": 330,
    "JST": 540,
    "CST_ASIA": 480,
    "AEST": 600,
    "AEDT": 660,
}


def normalize_timestamp(dt: datetime, source_timezone: str = "UTC") -> datetime:
    """Normalize a timestamp to a timezone-aware UTC datetime."""
    if dt.tzinfo is not None:
        offset = dt.tzinfo.utcoffset(dt)
        if offset == timedelta(0):
            return dt
        return dt.astimezone(timezone.utc)

    tz_obj = _resolve_zone(source_timezone)
    if tz_obj is not None:
        return dt.replace(tzinfo=tz_obj).astimezone(timezone.utc)

    offset = _get_offset(source_timezone)
    return dt.replace(tzinfo=timezone(timedelta(minutes=offset))).astimezone(timezone.utc)


def convert_timezone(dt: datetime, target_timezone: str) -> datetime:
    """Convert a UTC timestamp to a target timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    tz_obj = _resolve_zone(target_timezone)
    if tz_obj is not None:
        return dt.astimezone(tz_obj)
    return dt.astimezone(timezone(timedelta(minutes=_get_offset(target_timezone))))


def format_iso(dt: datetime) -> str:
    """Format a datetime as ISO 8601, using Z for UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.tzinfo.utcoffset(dt) == timedelta(0):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 string and normalize it to UTC."""
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO 8601 timestamp: {value!r}") from exc
    return normalize_timestamp(dt)


def _resolve_zone(timezone_name: str):
    """Resolve an IANA timezone; return None for fixed-offset names."""
    name = timezone_name.strip()
    if "/" not in name and name.upper() not in ("UTC", "GMT"):
        return None
    if name.upper() in ("UTC", "GMT"):
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise TimezoneResolutionError(f"Unknown IANA timezone: {timezone_name!r}") from None


def _get_offset(timezone_name: str) -> int:
    """Return a fixed UTC offset in minutes."""
    upper = timezone_name.upper().strip()
    if upper in _COMMON_OFFSETS:
        return _COMMON_OFFSETS[upper]

    stripped = timezone_name.strip()
    if stripped.startswith(("+", "-")) and ":" in stripped:
        try:
            sign = -1 if stripped.startswith("-") else 1
            hours_text, minutes_text = stripped[1:].split(":", 1)
            hours = int(hours_text)
            minutes = int(minutes_text)
        except ValueError:
            raise TimezoneResolutionError(
                f"Invalid numeric timezone offset: {timezone_name!r}"
            ) from None
        if hours < 0 or not (0 <= minutes < 60):
            raise TimezoneResolutionError(f"Invalid timezone offset: {timezone_name!r}")
        return sign * (hours * 60 + minutes)

    raise TimezoneResolutionError(f"Unknown timezone: {timezone_name!r}")
