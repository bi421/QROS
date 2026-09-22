"""
ResearchOS Macro Intelligence Layer - Base Interface
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class BaseInterface(ABC):
    """Base class for all MIL interfaces."""

    @abstractmethod
    def validate_contract(self) -> dict[str, Any]:
        """Validate interface contract compliance."""
        pass

    @abstractmethod
    def get_contract_version(self) -> str:
        """Get interface contract version."""
        pass


class QueryInterface(BaseInterface):
    """Base query interface."""

    @abstractmethod
    def query(self, query_type: str, params: dict) -> Any:
        """Execute a query."""
        pass


class BridgeInterface(BaseInterface):
    """Base bridge interface for V1 integration."""

    BRIDGE_VERSION = "v1"

    @abstractmethod
    def query(self, query_type: str, params: dict) -> Any:
        """Execute a query through the bridge."""
        pass

    @abstractmethod
    def validate_contract(self) -> dict[str, Any]:
        """Validate bridge contract compliance."""
        pass


class EventInterface(BaseInterface):
    """Base event interface."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[..., Any]) -> str:
        """Subscribe to events."""
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        pass

    @abstractmethod
    def publish(self, event: Any) -> None:
        """Publish an event."""
        pass
