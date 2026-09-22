"""
ResearchOS Macro Intelligence Layer - Event Timeline
Version: time/timeline/v1
Status: FROZEN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from researchos.macro.time.enums import (
    EventCategory,
    WindowType,
)
from researchos.macro.time.normalizer import UTC, TimeNormalizer


@dataclass(frozen=True)
class TimeWindow:
    """
    Time window for market reaction analysis.

    MIL-TIME-003: Market reaction windows are deterministic.
    """

    window_type: WindowType
    start: datetime
    end: datetime
    event_time: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "window_type": self.window_type.value,
            "start": TimeNormalizer.get_deterministic_timestamp(self.start),
            "end": TimeNormalizer.get_deterministic_timestamp(self.end),
            "event_time": TimeNormalizer.get_deterministic_timestamp(self.event_time),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeWindow:
        """Deserialize from dictionary."""
        return cls(
            window_type=WindowType(data["window_type"]),
            start=TimeNormalizer.parse_deterministic_timestamp(data["start"]),
            end=TimeNormalizer.parse_deterministic_timestamp(data["end"]),
            event_time=TimeNormalizer.parse_deterministic_timestamp(data["event_time"]),
        )

    def duration(self) -> timedelta:
        """Get window duration."""
        return self.end - self.start

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp is within window."""
        ts_utc = TimeNormalizer.to_utc(timestamp)
        return self.start <= ts_utc <= self.end


@dataclass(frozen=True)
class EventWindowSpec:
    """
    Specification for event windows.

    Supports:
    - T-1h, T-30m, T, T+30m, T+1h, T+4h, T+1d
    - Custom windows
    """

    pre_windows: list[timedelta] = field(
        default_factory=lambda: [
            timedelta(hours=1),
            timedelta(minutes=30),
        ]
    )
    post_windows: list[timedelta] = field(
        default_factory=lambda: [
            timedelta(minutes=30),
            timedelta(hours=1),
            timedelta(hours=4),
            timedelta(days=1),
        ]
    )
    custom_windows: dict[str, tuple[timedelta, timedelta]] = field(default_factory=dict)

    def generate_windows(self, event_time: datetime) -> list[TimeWindow]:
        """
        Generate time windows around an event.

        Returns:
            List of TimeWindow objects
        """
        windows: list[TimeWindow] = []
        event_utc = TimeNormalizer.to_utc(event_time)

        # Generate pre-event windows
        for offset in self.pre_windows:
            start = event_utc - offset
            end = event_utc
            windows.append(
                TimeWindow(
                    window_type=WindowType.PRE_EVENT,
                    start=start,
                    end=end,
                    event_time=event_utc,
                )
            )

        # Generate post-event windows
        for offset in self.post_windows:
            start = event_utc
            end = event_utc + offset
            windows.append(
                TimeWindow(
                    window_type=WindowType.POST_EVENT,
                    start=start,
                    end=end,
                    event_time=event_utc,
                )
            )

        # Generate custom windows
        for name, (start_offset, end_offset) in self.custom_windows.items():
            start = event_utc + start_offset
            end = event_utc + end_offset
            windows.append(
                TimeWindow(
                    window_type=WindowType.CUSTOM,
                    start=start,
                    end=end,
                    event_time=event_utc,
                    metadata={"name": name},
                )
            )

        # Sort by start time
        windows.sort(key=lambda w: w.start)

        return windows


@dataclass(frozen=True)
class CalendarEvent:
    """
    Single calendar event.

    Supports:
    - Scheduled releases
    - Unscheduled events
    - Recurring events
    - Holidays
    """

    # Identity
    event_id: str
    event_type: EventCategory

    # Timing
    scheduled_time: datetime
    actual_time: datetime | None = None
    duration: timedelta | None = None

    # Recurrence
    is_recurring: bool = False
    recurrence_pattern: str | None = None
    recurrence_end: datetime | None = None

    # Metadata
    title: str = ""
    description: str = ""
    series_ids: list[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    # Generated
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: str = "time/timeline/v1"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "scheduled_time": TimeNormalizer.get_deterministic_timestamp(self.scheduled_time),
            "actual_time": (TimeNormalizer.get_deterministic_timestamp(self.actual_time) if self.actual_time else None),
            "duration": self.duration.total_seconds() if self.duration else None,
            "is_recurring": self.is_recurring,
            "recurrence_pattern": self.recurrence_pattern,
            "recurrence_end": (TimeNormalizer.get_deterministic_timestamp(self.recurrence_end) if self.recurrence_end else None),
            "title": self.title,
            "description": self.description,
            "series_ids": sorted(self.series_ids),
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": TimeNormalizer.get_deterministic_timestamp(self.created_at),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        """Deserialize from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=EventCategory(data["event_type"]),
            scheduled_time=TimeNormalizer.parse_deterministic_timestamp(data["scheduled_time"]),
            actual_time=(TimeNormalizer.parse_deterministic_timestamp(data["actual_time"]) if data.get("actual_time") else None),
            duration=timedelta(seconds=data["duration"]) if data.get("duration") else None,
            is_recurring=data.get("is_recurring", False),
            recurrence_pattern=data.get("recurrence_pattern"),
            recurrence_end=(TimeNormalizer.parse_deterministic_timestamp(data["recurrence_end"]) if data.get("recurrence_end") else None),
            title=data.get("title", ""),
            description=data.get("description", ""),
            series_ids=data.get("series_ids", []),
            source=data.get("source", ""),
            confidence=data.get("confidence", 0.0),
            metadata=data.get("metadata", {}),
            created_at=TimeNormalizer.parse_deterministic_timestamp(data.get("created_at", TimeNormalizer.get_deterministic_timestamp(datetime.now(UTC)))),
            version=data.get("version", "time/timeline/v1"),
        )

    def to_json(self) -> str:
        """Serialize to JSON with deterministic ordering."""
        import json

        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, json_str: str) -> CalendarEvent:
        """Deserialize from JSON."""
        import json

        data = json.loads(json_str)
        return cls.from_dict(data)

    def compute_hash(self) -> str:
        """
        Compute deterministic hash.

        MIL-TIME-001: All timestamps are stored in UTC.
        """
        import hashlib

        hash_data = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "scheduled_time": TimeNormalizer.get_deterministic_timestamp(self.scheduled_time),
            "actual_time": (TimeNormalizer.get_deterministic_timestamp(self.actual_time) if self.actual_time else None),
            "is_recurring": self.is_recurring,
            "title": self.title,
            "series_ids": sorted(self.series_ids),
        }
        canonical = __import__("json").dumps(hash_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate the calendar event.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: list[str] = []

        # Validate event_id format
        if not self.event_id.startswith("EVT_"):
            errors.append("event_id must start with 'EVT_'")

        # Validate scheduled_time is in UTC
        if self.scheduled_time.tzinfo != UTC:
            errors.append("scheduled_time must be in UTC")

        # Validate actual_time >= scheduled_time if set
        if self.actual_time and self.actual_time < self.scheduled_time:
            errors.append("actual_time cannot be before scheduled_time")

        # Validate recurrence
        if self.is_recurring and not self.recurrence_pattern:
            errors.append("Recurring events require recurrence_pattern")

        return (len(errors) == 0, errors)


@dataclass(frozen=True)
class EventTimeline:
    """
    Complete event timeline.

    Supports:
    - Event ordering
    - Overlapping events
    - Event windows
    """

    timeline_id: str
    events: list[CalendarEvent] = field(default_factory=list)
    window_spec: EventWindowSpec = field(default_factory=EventWindowSpec)

    def __post_init__(self):
        """Validate the timeline."""
        # Sort events by scheduled_time
        sorted_events = sorted(self.events, key=lambda e: e.scheduled_time)
        object.__setattr__(self, "events", sorted_events)

        # Verify no overlapping events
        self._verify_no_overlaps()

    def _verify_no_overlaps(self) -> None:
        """Verify no overlapping events."""
        for i in range(len(self.events) - 1):
            current = self.events[i]
            next_event = self.events[i + 1]

            # Check if current event overlaps with next
            current_end = current.scheduled_time + current.duration if current.duration else current.scheduled_time + timedelta(minutes=30)

            if next_event.scheduled_time < current_end:
                raise ValueError(f"Overlapping events: {current.event_id} and {next_event.event_id}")

    def add_event(self, event: CalendarEvent) -> EventTimeline:
        """
        Add an event to the timeline.

        Returns:
            New timeline with event added
        """
        new_events = self.events + [event]
        return EventTimeline(
            timeline_id=self.timeline_id,
            events=new_events,
            window_spec=self.window_spec,
        )

    def get_event(self, event_id: str) -> CalendarEvent | None:
        """Get event by ID."""
        for event in self.events:
            if event.event_id == event_id:
                return event
        return None

    def get_events_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        """Get events in time range."""
        start_utc = TimeNormalizer.to_utc(start)
        end_utc = TimeNormalizer.to_utc(end)

        return [event for event in self.events if start_utc <= event.scheduled_time <= end_utc]

    def generate_windows(self, event_id: str) -> list[TimeWindow]:
        """
        Generate windows for an event.

        Returns:
            List of TimeWindow objects
        """
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        return self.window_spec.generate_windows(event.scheduled_time)

    def get_event_count(self) -> int:
        """Get total number of events."""
        return len(self.events)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """
        Verify timeline integrity.

        MIL-TIME-002: Release history is immutable.

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Check for duplicate event IDs
        event_ids = [e.event_id for e in self.events]
        if len(event_ids) != len(set(event_ids)):
            errors.append("Duplicate event IDs detected")

        # Validate each event
        for event in self.events:
            is_valid, event_errors = event.validate()
            if not is_valid:
                errors.extend(event_errors)

        return (len(errors) == 0, errors)
