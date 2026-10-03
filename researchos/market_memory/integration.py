"""
Market Memory Integration Layer — adapter interfaces for connecting to
ResearchCycle, ReasoningChain, Validation, Experiment Framework, and
Macro Intelligence.

Uses adapter/interfaces pattern to avoid hard coupling.
All integrations are optional and non-breaking.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class IntegrationContext:
    """
    Context object for market memory integration.

    Carries references to external system components through
    callable interfaces, avoiding direct imports and hard coupling.
    """

    research_cycle_adapter: Callable[..., dict[str, Any]] | None = None
    reasoning_chain_adapter: Callable[..., dict[str, Any]] | None = None
    validation_adapter: Callable[..., dict[str, Any]] | None = None
    experiment_framework_adapter: Callable[..., dict[str, Any]] | None = None
    macro_intelligence_adapter: Callable[..., dict[str, Any]] | None = None
    evidence_registry_adapter: Callable[..., dict[str, Any]] | None = None
    audit_entry_adapter: Callable[..., dict[str, Any]] | None = None


class MarketMemoryIntegrator:
    """
    Optional integration layer for market memory.

    Connects to external systems through adapters. If no adapters
    are provided, the integrator operates in standalone mode.

    Args:
        context: IntegrationContext with optional adapters.
    """

    def __init__(self, context: IntegrationContext | None = None):
        self.context = context or IntegrationContext()

    def connect_to_research_cycle(self, cycle_id: str, memory_report_id: str) -> dict[str, Any]:
        """
        Connect a market memory report to a research cycle.

        Args:
            cycle_id: The ResearchCycle ID.
            memory_report_id: The MarketMemoryReport ID.

        Returns:
            Dict with connection status.
        """
        if self.context.research_cycle_adapter:
            return self.context.research_cycle_adapter(cycle_id, memory_report_id)
        return {"status": "standalone", "note": "No research cycle adapter configured"}

    def connect_to_reasoning_chain(self, chain_id: str, match_results: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Connect match results to a reasoning chain.

        Args:
            chain_id: The ReasoningChain ID.
            match_results: List of match result dicts.

        Returns:
            Dict with connection status.
        """
        if self.context.reasoning_chain_adapter:
            return self.context.reasoning_chain_adapter(chain_id, match_results)
        return {"status": "standalone", "note": "No reasoning chain adapter configured"}

    def connect_to_validation(self, validation_id: str, memory_report_id: str) -> dict[str, Any]:
        """
        Connect a market memory report to validation.

        Args:
            validation_id: The Validation ID.
            memory_report_id: The MarketMemoryReport ID.

        Returns:
            Dict with connection status.
        """
        if self.context.validation_adapter:
            return self.context.validation_adapter(validation_id, memory_report_id)
        return {"status": "standalone", "note": "No validation adapter configured"}

    def connect_to_experiment(self, experiment_id: str, memory_report_id: str) -> dict[str, Any]:
        """
        Connect a market memory report to an experiment.

        Args:
            experiment_id: The Experiment ID.
            memory_report_id: The MarketMemoryReport ID.

        Returns:
            Dict with connection status.
        """
        if self.context.experiment_framework_adapter:
            return self.context.experiment_framework_adapter(experiment_id, memory_report_id)
        return {"status": "standalone", "note": "No experiment framework adapter configured"}

    def connect_to_macro_intelligence(self, macro_id: str, memory_report_id: str) -> dict[str, Any]:
        """
        Connect a market memory report to macro intelligence.

        Args:
            macro_id: The Macro analysis ID.
            memory_report_id: The MarketMemoryReport ID.

        Returns:
            Dict with connection status.
        """
        if self.context.macro_intelligence_adapter:
            return self.context.macro_intelligence_adapter(macro_id, memory_report_id)
        return {"status": "standalone", "note": "No macro intelligence adapter configured"}

    def register_evidence(self, evidence_ids: list[str], memory_report_id: str) -> dict[str, Any]:
        """
        Register evidence references for a market memory report.

        Args:
            evidence_ids: List of evidence IDs.
            memory_report_id: The MarketMemoryReport ID.

        Returns:
            Dict with connection status.
        """
        if self.context.evidence_registry_adapter:
            return self.context.evidence_registry_adapter(evidence_ids, memory_report_id)
        return {"status": "standalone", "note": "No evidence registry adapter configured"}

    def create_audit_entry(self, action: str, object_id: str, details: str = "") -> dict[str, Any]:
        """
        Create an audit entry through the adapter.

        Args:
            action: The action performed.
            object_id: The affected object ID.
            details: Additional details.

        Returns:
            Dict with audit entry status.
        """
        if self.context.audit_entry_adapter:
            return self.context.audit_entry_adapter(action, object_id, details)
        return {"status": "standalone", "note": "No audit entry adapter configured"}
