"""Provenance-bound execution boundary for deterministic research.

The public research API accepts only ``ResearchInput`` plus a resolver that
materializes the already-validated dataset reference.  Raw ``HistoricalDataset``
objects therefore remain inside the data layer and cannot become an accidental
research execution input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from researchos.data_engine.boundary import ValidatedDatasetRef
from researchos.data_engine.research_reader import ResearchSeries
from researchos.research_boundary import ResearchInput


class ResearchDataResolver(Protocol):
    """Resolve a validated dataset reference into research-safe series."""

    def resolve(self, reference: ValidatedDatasetRef) -> ResearchSeries:
        ...


def _canonical(value: Any) -> Any:
    """Convert supported result values into a deterministic JSON form."""
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)


def _result_payload(result: Any) -> Any:
    """Serialize a research result through its public ``to_dict`` contract."""
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    return _canonical(result)


def execution_hash(
    *,
    research_id: str,
    dataset_id: str,
    dataset_content_hash: str,
    dataset_hash: str,
    methodology_version: str,
    result: Any,
) -> str:
    """Return a deterministic SHA-256 identity for one research execution."""
    payload = {
        "research_id": research_id,
        "dataset_id": dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "dataset_hash": dataset_hash,
        "methodology_version": methodology_version,
        "result": _result_payload(result),
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class ResearchExecutionResult:
    """Immutable envelope binding a research result to its input identity."""

    research_id: str
    dataset_id: str
    dataset_content_hash: str
    dataset_hash: str
    methodology_version: str
    result: Any
    execution_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "research_id",
            "dataset_id",
            "dataset_content_hash",
            "dataset_hash",
            "methodology_version",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        object.__setattr__(
            self,
            "execution_hash",
            execution_hash(
                research_id=self.research_id,
                dataset_id=self.dataset_id,
                dataset_content_hash=self.dataset_content_hash,
                dataset_hash=self.dataset_hash,
                methodology_version=self.methodology_version,
                result=self.result,
            ),
        )

    def verify_integrity(self) -> bool:
        """Verify that the stored execution hash still matches the envelope."""
        return self.execution_hash == execution_hash(
            research_id=self.research_id,
            dataset_id=self.dataset_id,
            dataset_content_hash=self.dataset_content_hash,
            dataset_hash=self.dataset_hash,
            methodology_version=self.methodology_version,
            result=self.result,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_id": self.research_id,
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "dataset_hash": self.dataset_hash,
            "methodology_version": self.methodology_version,
            "result": _result_payload(self.result),
            "execution_hash": self.execution_hash,
        }


class ResearchExecutor:
    """Execute a research operation through the validated-data boundary."""

    def __init__(self, resolver: ResearchDataResolver):
        self._resolver = resolver

    def execute(
        self,
        research_input: ResearchInput,
        operation: Callable[[ResearchSeries, Any], Any],
        config: Any = None,
    ) -> ResearchExecutionResult:
        """Resolve validated data and execute the supplied scientific operation.

        ``operation`` receives only ``ResearchSeries`` and configuration; it
        never receives ``HistoricalDataset``.  The caller controls the
        scientific implementation while this boundary controls provenance.
        """
        if not isinstance(research_input, ResearchInput):
            raise TypeError("research execution requires ResearchInput")

        series = self._resolver.resolve(research_input.dataset)
        result = operation(series, config)
        return ResearchExecutionResult(
            research_id=research_input.research_id,
            dataset_id=research_input.dataset.dataset_id,
            dataset_content_hash=research_input.dataset.dataset_content_hash,
            dataset_hash=research_input.dataset.dataset_hash,
            methodology_version=research_input.methodology_version,
            result=result,
        )


__all__ = [
    "ResearchDataResolver",
    "ResearchExecutionResult",
    "ResearchExecutor",
    "execution_hash",
]
