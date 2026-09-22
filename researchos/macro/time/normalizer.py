"""
ResearchOS Macro Intelligence Layer - Time Normalization
Version: time/normalize/v1
Status: FROZEN
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import overload

UTC = timezone.utc


class TimeNormalizer:
    """
    Deterministic time normalization utilities.

    MIL-TIME-001: All timestamps are stored in UTC.
    MIL-TIME-004: Calendar reconstruction is reproducible.
    """

    @staticmethod
    @overload
    def to_utc(dt: None) -> None: ...

    @staticmethod
    @overload
    def to_utc(dt: datetime) -> datetime: ...

    @staticmethod
    def to_utc(dt: datetime | None) -> datetime | None:
        """
        Convert datetime to UTC.

        Rules:
        - If naive (no timezone), assume UTC
        - If aware, convert to UTC
        - Preserve timezone information
        - Handle DST transitions safely
        """
        if dt is None:
            return None

        # If already UTC, return as-is
        if dt.tzinfo == UTC:
            return dt

        # If naive, assume UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)

        # Convert to UTC
        return dt.astimezone(UTC)

    @staticmethod
    def _require_utc(dt: datetime) -> datetime:
        """Normalize a concrete datetime and preserve a non-optional type."""
        utc_dt = TimeNormalizer.to_utc(dt)
        assert utc_dt is not None
        return utc_dt

    @staticmethod
    def normalize_timestamp(dt: datetime | None) -> datetime | None:
        """
        Normalize timestamp to UTC with second precision.

        Rules:
        - Convert to UTC
        - Round down to nearest second
        - Remove microseconds
        """
        if dt is None:
            return None

        utc_dt = TimeNormalizer._require_utc(dt)

        # Round down to nearest second
        return utc_dt.replace(microsecond=0)

    @staticmethod
    def normalize_to_minute(dt: datetime | None) -> datetime | None:
        """
        Normalize timestamp to UTC with minute precision.

        Rules:
        - Convert to UTC
        - Round down to nearest minute
        - Remove seconds and microseconds
        """
        if dt is None:
            return None

        utc_dt = TimeNormalizer.to_utc(dt)

        # Round down to nearest minute
        return utc_dt.replace(second=0, microsecond=0)

    @staticmethod
    def normalize_to_hour(dt: datetime | None) -> datetime | None:
        """
        Normalize timestamp to UTC with hour precision.

        Rules:
        - Convert to UTC
        - Round down to nearest hour
        - Remove minutes, seconds, and microseconds
        """
        if dt is None:
            return None

        utc_dt = TimeNormalizer.to_utc(dt)

        # Round down to nearest hour
        return utc_dt.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def normalize_to_day(dt: datetime | None) -> datetime | None:
        """
        Normalize timestamp to UTC with day precision.

        Rules:
        - Convert to UTC
        - Round down to start of day
        - Remove time components
        """
        if dt is None:
            return None

        utc_dt = TimeNormalizer.to_utc(dt)

        # Round down to start of day
        return utc_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def is_dst_transition(dt: datetime) -> bool:
        """
        Check if datetime is during DST transition.

        Returns:
            True if during DST transition
        """
        # Check if timezone has DST
        tz = dt.tzinfo
        if tz is None:
            return False

        # Try to determine if this is a DST transition
        # by checking if the UTC offset changes
        try:
            # Create two datetimes 1 second apart
            dt1 = dt.replace(microsecond=0)
            dt2 = dt1 + timedelta(seconds=1)

            offset1 = dt1.utcoffset()
            offset2 = dt2.utcoffset()

            if offset1 and offset2 and offset1 != offset2:
                return True
        except (ValueError, OSError):
            pass

        return False

    @staticmethod
    def safe_add_hours(dt: datetime, hours: int) -> datetime:
        """
        Safely add hours to datetime, handling DST transitions.

        Returns:
            New datetime with hours added
        """
        utc_dt = TimeNormalizer.to_utc(dt)
        return utc_dt + timedelta(hours=hours)

    @staticmethod
    def safe_add_days(dt: datetime, days: int) -> datetime:
        """
        Safely add days to datetime, handling DST transitions.

        Returns:
            New datetime with days added
        """
        utc_dt = TimeNormalizer.to_utc(dt)
        return utc_dt + timedelta(days=days)

    @staticmethod
    def get_business_hours(
        dt: datetime,
        start_hour: int = 9,
        end_hour: int = 16,
    ) -> tuple[datetime, datetime]:
        """
        Get business hours for a given datetime.

        Returns:
            (business_start, business_end) in UTC
        """
        utc_dt = TimeNormalizer.to_utc(dt)

        # Get start of business day
        business_start = utc_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)

        # Get end of business day
        business_end = utc_dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        # If start is after end, it means we crossed midnight
        if business_start > business_end:
            business_end += timedelta(days=1)

        return business_start, business_end

    @staticmethod
    def is_trading_day(dt: datetime) -> bool:
        """
        Check if datetime falls on a trading day.

        Rules:
        - Monday-Friday
        - Not a holiday
        - During trading hours
        """
        utc_dt = TimeNormalizer.to_utc(dt)

        # Check if weekend (5=Saturday, 6=Sunday)
        if utc_dt.weekday() >= 5:
            return False

        # Note: Holiday checking would require a holiday calendar
        # For now, we assume all weekdays are trading days

        return True

    @staticmethod
    def get_next_trading_day(dt: datetime) -> datetime:
        """
        Get the next trading day.

        Returns:
            Next trading day at 00:00 UTC
        """
        utc_dt = TimeNormalizer.to_utc(dt)

        # Start from next day
        next_day = utc_dt + timedelta(days=1)
        next_day = next_day.replace(hour=0, minute=0, second=0, microsecond=0)

        # Skip weekends
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)

        return next_day

    @staticmethod
    def get_previous_trading_day(dt: datetime) -> datetime:
        """
        Get the previous trading day.

        Returns:
            Previous trading day at 00:00 UTC
        """
        utc_dt = TimeNormalizer.to_utc(dt)

        # Start from previous day
        prev_day = utc_dt - timedelta(days=1)
        prev_day = prev_day.replace(hour=0, minute=0, second=0, microsecond=0)

        # Skip weekends
        while prev_day.weekday() >= 5:
            prev_day -= timedelta(days=1)

        return prev_day

    @staticmethod
    def calculate_window(
        event_time: datetime,
        window_type: str,
        offset: timedelta = timedelta(0),
    ) -> tuple[datetime, datetime]:
        """
        Calculate a time window around an event.

        Args:
            event_time: Event timestamp (will be converted to UTC)
            window_type: Type of window (pre, post, full)
            offset: Additional offset

        Returns:
            (window_start, window_end) in UTC
        """
        event_utc = TimeNormalizer._require_utc(event_time)

        if window_type == "pre":
            start = event_utc + offset - timedelta(hours=1)
            end = event_utc + offset
        elif window_type == "post":
            start = event_utc + offset
            end = event_utc + offset + timedelta(hours=1)
        elif window_type == "full":
            start = event_utc + offset - timedelta(hours=1)
            end = event_utc + offset + timedelta(hours=1)
        else:
            start = event_utc + offset
            end = event_utc + offset + timedelta(hours=1)

        return start, end

    @staticmethod
    def get_deterministic_timestamp(dt: datetime) -> str:
        """
        Get deterministic timestamp string.

        Rules:
        - Always UTC
        - ISO 8601 format
        - No timezone abbreviation
        - Consistent across runs
        """
        utc_dt = TimeNormalizer.to_utc(dt)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    @staticmethod
    def parse_deterministic_timestamp(ts: str) -> datetime:
        """
        Parse deterministic timestamp string.

        Returns:
            UTC datetime
        """
        # Parse ISO 8601 format
        dt = datetime.fromisoformat(ts)

        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return TimeNormalizer.to_utc(dt)
