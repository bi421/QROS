"""
Timezone normalization utilities for market data.

Based on Article XVII: Object Model — Data Layer.

All timestamps in ResearchOS are normalized to UTC on load.
This module provides utilities for converting timestamps from
various timezones to UTC.

Guarantees:
    - Deterministic: Same input timestamp → same UTC output
    - Safe: Handles naive and aware datetimes correctly
    - Standard: All timestamps are ISO 8601 compliant
    - Explicit: Unknown or invalid timezone names raise
      ``TimezoneResolutionError`` — never a silent UTC fallback

Resolution order for a timezone name:
    1. Common abbreviation table (fixed offsets; e.g. "EST", "CET")
    2. Explicit numeric offset (e.g. "+05:30", "-05:00")
    3. IANA zone name via ``zoneinfo`` (e.g. "America/New_York"),
       with DST handled by the IANA database — no assumptions
Anything else is an error.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimezoneResolutionError(ValueError):
    """Raised when a timezone name cannot be resolved.

    Scientific-integrity guarantee: an unresolvable timezone is an
    explicit error. It must NEVER be silently treated as UTC, because
    a mis-normalized timestamp corrupts every downstream computation
    and dataset hash while appearing perfectly valid.
    """


# Common timezone offsets (minutes from UTC)
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


def normalize_timestamp(
    dt: datetime,
    source_timezone: str = "UTC",
) -> datetime:
    """
    Normalize a timestamp to UTC.

    Args:
        dt: The datetime to normalize. Can be naive or timezone-aware.
        source_timezone: Source timezone: a known abbreviation
            (e.g. "EST"), a numeric offset (e.g. "+05:30"), or an IANA
            zone name (e.g. "America/New_York").

    Returns:
        Timezone-aware datetime in UTC.

    Raises:
        TimezoneResolutionError: If ``source_timezone`` cannot be
            resolved. Never silently substitutes UTC.

    Examples:
        >>> normalize_timestamp(datetime(2024, 1, 1, 12, 0, 0), "EST")
        datetime(2024, 1, 1, 17, 0, 0, tzinfo=timezone.utc)

        >>> normalize_timestamp(datetime(2024, 1, 1, 12, 0, 0), tzinfo=timezone.utc)
        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        Naive input with an IANA zone is interpreted as local wall
        time in that zone (DST per the IANA database):
        >>> normalize_timestamp(datetime(2024, 3, 10, 3, 0, 0), "America/New_York")
        datetime(2024, 3, 10, 7, 0, 0, tzinfo=timezone.utc)
    """
    # If already timezone-aware, convert to UTC
    if dt.tzinfo is not None:
        offset = dt.tzinfo.utcoffset(dt)
        if offset == timedelta(0):
            return dt
        return dt.astimezone(timezone.utc)

    # Naive datetime: apply source timezone
    # IANA zone: interpret naive input as local wall time in that zone
    tz_obj = _resolve_zone(source_timezone)
    if tz_obj is not None:
        aware = dt.replace(tzinfo=tz_obj)
        return aware.astimezone(timezone.utc)

    offset = _get_offset(source_timezone)
    if offset == 0:
        return dt.replace(tzinfo=timezone.utc)

    # Create timezone-aware datetime and convert to UTC
    tz = timezone(timedelta(minutes=offset))
    aware = dt.replace(tzinfo=tz)
    return aware.astimezone(timezone.utc)


def convert_timezone(
    dt: datetime,
    target_timezone: str,
) -> datetime:
    """
    Convert a UTC timestamp to a target timezone.

    Args:
        dt: UTC datetime to convert.
        target_timezone: Target timezone: abbreviation, numeric
            offset, or IANA zone name.

    Returns:
        Timezone-aware datetime in the target timezone.

    Raises:
        TimezoneResolutionError: If ``target_timezone`` cannot be
            resolved.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    tz_obj = _resolve_zone(target_timezone)
    if tz_obj is not None:
        return dt.astimezone(tz_obj)

    offset = _get_offset(target_timezone)
    tz = timezone(timedelta(minutes=offset))
    return dt.astimezone(tz)


def format_iso(dt: datetime) -> str:
    """
    Format a datetime as ISO 8601 string with Z suffix for UTC.

    Args:
        dt: Datetime to format.

    Returns:
        ISO 8601 formatted string.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if dt.tzinfo.utcoffset(dt) == timedelta(0):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    """
    Parse an ISO 8601 string, normalizing to UTC.

    Args:
        value: ISO 8601 formatted string.

    Returns:
        Timezone-aware datetime in UTC.
    """
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO 8601 timestamp: {value!r}") from exc
    return normalize_timestamp(dt)


def _resolve_zone(timezone_name: str):
    """Resolve an IANA zone name to a ``ZoneInfo``.

    Returns None if the name is not an IANA zone candidate (callers
    then try abbreviations / numeric offsets). Raises
    ``TimezoneResolutionError`` for names that LOOK like IANA zones
    but do not exist, so typos fail loudly.
    """
    name = timezone_name.strip()
    # IANA names contain "/" or are well-known zone ids; abbreviations
    # and numeric offsets are handled by _get_offset.
    if "/" not in name and name not in ("UTC", "GMT"):
        return None
    if name.upper() in ("UTC", "GMT"):
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise TimezoneResolutionError(
            f"Unknown IANA timezone: {timezone_name!r}. Timezone names "
            "must be a known abbreviation (e.g. 'EST'), a numeric "
            "offset (e.g. '+05:30'), or a valid IANA zone "
            "(e.g. 'America/New_York'). Never silently treated as UTC."
        ) from None


def _get_offset(timezone_name: str) -> int:
    """
    Get UTC offset in minutes for a fixed-offset timezone name.

    Args:
        timezone_name: Timezone name (e.g., "EST", "CET") or numeric
            offset (e.g., "+05:30").

    Returns:
        Offset in minutes from UTC (positive = east of UTC).

    Raises:
        TimezoneResolutionError: If the name matches no abbreviation
            and no valid numeric offset. Never returns a silent 0.
    """
    # Try common abbreviations
    upper = timezone_name.upper().strip()
    if upper in _COMMON_OFFSETS:
        return _COMMON_OFFSETS[upper]

    # Try to parse hours offset (e.g., "+05:30", "-05:00")
    stripped = timezone_name.strip()
    if stripped.startswith(("+", "-")) and ":" in stripped:
        try:
            parts = stripped.split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= minutes < 60):
                raise TimezoneResolutionError(
                    f"Invalid timezone offset minutes in {timezone_name!r} "
                    "(minutes must be in [0, 60))."
                )
            if hours < 0:
                return hours * 60 - minutes
            if hours > 0:
                return hours * 60 + minutes
            return -minutes if stripped.startswith("-") else minutes
        except ValueError as exc:
            raise TimezoneResolutionError(
                f"Invalid numeric timezone offset: {timezone_name!r} ({exc})."
            ) from None

    raise TimezoneResolutionError(
        f"Unknown timezone: {timezone_name!r}. Must be a known "
        "abbreviation (e.g. 'EST'), a numeric offset (e.g. '+05:30'), "
        "or a valid IANA zone (e.g. 'America/New_York'). Never "
        "silently treated as UTC."
    )
