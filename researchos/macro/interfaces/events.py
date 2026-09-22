"""
ResearchOS Macro Intelligence Layer - Event Subscription Interface
Version: esi/v1
Status: FROZEN
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from researchos.macro.interfaces.base import EventInterface


class MacroEventBus(EventInterface, ABC):
    """
    In-process event bus for macro events.

    Usage:
        bus = MacroEventBusImpl()
        bus.subscribe("FOMC_MEETING", handler_function)
        bus.publish(event)
    """

    EVENT_VERSION = "esi/v1"

    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: Callable[..., Any],
    ) -> str:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function to invoke

        Returns:
            Subscription ID for later unsubscription
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from events.

        Returns:
            True if subscription was found and removed
        """
        pass

    @abstractmethod
    def publish(self, event: Any) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event: The event object to publish
        """
        pass

    @abstractmethod
    def publish_batch(self, events: list[Any]) -> None:
        """
        Publish multiple events atomically.

        Args:
            events: List of events to publish
        """
        pass

    @abstractmethod
    def get_subscribers(self, event_type: str) -> list[str]:
        """
        Get all subscription IDs for an event type.

        Returns:
            List of subscription IDs
        """
        pass

    @abstractmethod
    def get_event_types(self) -> list[str]:
        """
        Get all event types with subscribers.

        Returns:
            List of event type strings
        """
        pass

    @abstractmethod
    def get_subscription_count(self) -> int:
        """
        Get total number of active subscriptions.

        Returns:
            Count of active subscriptions
        """
        pass

    # =====================================================================
    # INTERFACE METHODS
    # =====================================================================

    def validate_contract(self) -> dict[str, Any]:
        """Validate interface contract compliance."""
        return {
            "is_valid": True,
            "version": self.EVENT_VERSION,
            "interface": "MacroEventBus",
            "methods_count": len([m for m in dir(self) if not m.startswith("_")]),
        }

    def get_contract_version(self) -> str:
        """Get interface contract version."""
        return self.EVENT_VERSION
