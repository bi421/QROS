"""
ResearchOS Macro Intelligence Layer - Economic Calendar
Version: time/calendar/v1
Status: FROZEN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from researchos.macro.time.enums import (
    EventCategory,
)
from researchos.macro.time.normalizer import UTC, TimeNormalizer
from researchos.macro.time.timeline import CalendarEvent


@dataclass(frozen=True)
class MarketHoliday:
    """
    Market holiday definition.
    """

    holiday_id: str
    date: datetime
    name: str
    markets_affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "holiday_id": self.holiday_id,
            "date": self.date.strftime("%Y-%m-%d"),
            "name": self.name,
            "markets_affected": sorted(self.markets_affected),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketHoliday:
        """Deserialize from dictionary."""
        return cls(
            holiday_id=data["holiday_id"],
            date=datetime.strptime(data["date"], "%Y-%m-%d").replace(tzinfo=UTC),
            name=data["name"],
            markets_affected=data.get("markets_affected", []),
        )


@dataclass(frozen=True)
class RecurringEventPattern:
    """
    Pattern for recurring events.

    Supports:
    - Daily
    - Weekly
    - Monthly
    - Quarterly
    - Annual
    """

    pattern_type: str  # "daily", "weekly", "monthly", etc.
    interval: int = 1
    day_of_week: int | None = None  # 0=Monday, 6=Sunday
    day_of_month: int | None = None
    month: int | None = None
    quarter: int | None = None

    def get_next_occurrence(self, from_date: datetime) -> datetime:
        """
        Get next occurrence after from_date.

        Returns:
            Next occurrence in UTC
        """
        current = TimeNormalizer.to_utc(from_date)

        if self.pattern_type == "daily":
            return current + timedelta(days=self.interval)

        elif self.pattern_type == "weekly":
            days_until = (7 - current.weekday() + self.interval * 7) % 7
            if days_until == 0:
                days_until = 7
            return current + timedelta(days=days_until)

        elif self.pattern_type == "monthly":
            # Move to next month
            month = current.month + self.interval
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current.day, 28)  # Safe day for all months

            try:
                return current.replace(year=year, month=month, day=day)
            except ValueError:
                # Handle months with fewer days
                return current.replace(year=year, month=month, day=28)

        # Add more patterns as needed
        return current + timedelta(days=30)


@dataclass(frozen=True)
class EconomicCalendar:
    """
    Complete economic calendar.

    MIL-TIME-004: Calendar reconstruction is reproducible.
    """

    # Identity
    calendar_id: str
    year: int
    month: int | None = None

    # Events
    events: list[CalendarEvent] = field(default_factory=list)
    holidays: list[MarketHoliday] = field(default_factory=list)

    # Recurring patterns
    recurring_patterns: list[RecurringEventPattern] = field(default_factory=list)

    # Metadata
    source: str = ""
    version: str = "time/calendar/v1"

    def __post_init__(self):
        """Validate the calendar."""
        # Sort events by scheduled_time
        sorted_events = sorted(self.events, key=lambda e: e.scheduled_time)
        object.__setattr__(self, "events", sorted_events)

        # Sort holidays by date
        sorted_holidays = sorted(self.holidays, key=lambda h: h.date)
        object.__setattr__(self, "holidays", sorted_holidays)

    def add_event(self, event: CalendarEvent) -> EconomicCalendar:
        """
        Add an event to the calendar.

        Returns:
            New calendar with event added
        """
        new_events = self.events + [event]
        return EconomicCalendar(
            calendar_id=self.calendar_id,
            year=self.year,
            month=self.month,
            events=new_events,
            holidays=self.holidays,
            recurring_patterns=self.recurring_patterns,
            source=self.source,
            version=self.version,
        )

    def add_holiday(self, holiday: MarketHoliday) -> EconomicCalendar:
        """
        Add a holiday to the calendar.

        Returns:
            New calendar with holiday added
        """
        new_holidays = self.holidays + [holiday]
        return EconomicCalendar(
            calendar_id=self.calendar_id,
            year=self.year,
            month=self.month,
            events=self.events,
            holidays=new_holidays,
            recurring_patterns=self.recurring_patterns,
            source=self.source,
            version=self.version,
        )

    def get_events(self) -> list[CalendarEvent]:
        """Get all events."""
        return self.events

    def get_events_by_type(
        self,
        event_type: EventCategory,
    ) -> list[CalendarEvent]:
        """Get events by type."""
        return [event for event in self.events if event.event_type == event_type]

    def get_events_by_series(
        self,
        series_id: str,
    ) -> list[CalendarEvent]:
        """Get events for a specific series."""
        return [event for event in self.events if series_id in event.series_ids]

    def get_holidays(self) -> list[MarketHoliday]:
        """Get all holidays."""
        return self.holidays

    def is_holiday(self, date: datetime) -> bool:
        """
        Check if date is a holiday.

        Returns:
            True if date is a holiday
        """
        date_only = TimeNormalizer.to_utc(date).date()

        for holiday in self.holidays:
            if holiday.date.date() == date_only:
                return True

        return False

    def is_trading_day(self, date: datetime) -> bool:
        """
        Check if date is a trading day.

        Returns:
            True if date is a trading day
        """
        utc_dt = TimeNormalizer.to_utc(date)

        # Check if weekend
        if utc_dt.weekday() >= 5:
            return False

        # Check if holiday
        if self.is_holiday(date):
            return False

        return True

    def get_next_trading_day(self, from_date: datetime) -> datetime:
        """
        Get next trading day.

        Returns:
            Next trading day at 00:00 UTC
        """
        current = TimeNormalizer.to_utc(from_date)
        current = current.replace(hour=0, minute=0, second=0, microsecond=0)

        while True:
            current += timedelta(days=1)
            if self.is_trading_day(current):
                return current

    def get_previous_trading_day(self, from_date: datetime) -> datetime:
        """
        Get previous trading day.

        Returns:
            Previous trading day at 00:00 UTC
        """
        current = TimeNormalizer.to_utc(from_date)
        current = current.replace(hour=0, minute=0, second=0, microsecond=0)

        while True:
            current -= timedelta(days=1)
            if self.is_trading_day(current):
                return current

    def get_events_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        """Get events in time range."""
        start_utc = TimeNormalizer.to_utc(start)
        end_utc = TimeNormalizer.to_utc(end)

        return [event for event in self.events if start_utc <= event.scheduled_time <= end_utc]

    def get_recurring_occurrences(
        self,
        pattern: RecurringEventPattern,
        from_date: datetime,
        to_date: datetime,
        max_occurrences: int = 100,
    ) -> list[datetime]:
        """
        Get occurrences of a recurring pattern.

        Returns:
            List of occurrence datetimes
        """
        occurrences: list[datetime] = []
        current = TimeNormalizer.to_utc(from_date)
        end_utc = TimeNormalizer.to_utc(to_date)

        while current <= end_utc and len(occurrences) < max_occurrences:
            occurrences.append(current)
            current = pattern.get_next_occurrence(current)

        return occurrences

    def get_event_count(self) -> int:
        """Get total number of events."""
        return len(self.events)

    def get_holiday_count(self) -> int:
        """Get total number of holidays."""
        return len(self.holidays)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "calendar_id": self.calendar_id,
            "year": self.year,
            "month": self.month,
            "event_count": len(self.events),
            "holiday_count": len(self.holidays),
            "recurring_patterns": len(self.recurring_patterns),
            "source": self.source,
            "version": self.version,
        }

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """
        Verify calendar integrity.

        MIL-TIME-004: Calendar reconstruction is reproducible.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: list[str] = []

        # Check for duplicate event IDs
        event_ids = [e.event_id for e in self.events]
        if len(event_ids) != len(set(event_ids)):
            errors.append("Duplicate event IDs detected")

        # Check for duplicate holiday IDs
        holiday_ids = [h.holiday_id for h in self.holidays]
        if len(holiday_ids) != len(set(holiday_ids)):
            errors.append("Duplicate holiday IDs detected")

        # Validate each event
        for event in self.events:
            is_valid, event_errors = event.validate()
            if not is_valid:
                errors.extend(event_errors)

        # Check for overlapping events
        for i in range(len(self.events) - 1):
            current = self.events[i]
            next_event = self.events[i + 1]

            if next_event.scheduled_time < current.scheduled_time:
                errors.append(f"Events not sorted: {next_event.event_id} before {current.event_id}")

        return (len(errors) == 0, errors)
