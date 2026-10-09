"""
Backend scheduling â€” deterministic, profile-driven candidate selection.

Phase 4.4: intelligent backend scheduling & production hardening.

The scheduler turns ``BackendRouter`` from static first-match routing into an
adaptive production scheduler while preserving the ResearchOS determinism
contract (identical inputs + identical router configuration â†’ identical
output and ``result_hash``).

Selection is a **pure function** of four signals:

    1. ``dataset size`` â€” binned into a ``DatasetSizeClass``
       (SMALL / MEDIUM / LARGE) via deterministic thresholds.
    2. ``operation complexity`` â€” a static per-operation complexity class
       (light / standard / heavy) used for diagnostics and default seeding.
    3. ``backend capability`` â€” the candidate's advertised
       ``BackendCapabilities`` (operation support + trust-boundary guarantees).
    4. ``historical performance`` â€” a ``CertifiedPerformanceProfile``: a
       versioned table of measured per-(backend, operation, size-class)
       runtimes. The profile is seeded from the official benchmark
       (``researchos.benchmarks.benchmark_cpp``) and only changes via an
       explicit ``recalibrate`` action (which bumps ``profile_version``), so
       decisions stay reproducible for identical router configuration.

Runtime telemetry (``ExecutionHistory``) records every execution's observed
duration, chosen backend, fallback count, and validation outcome.  It is
**observational** â€” it is never part of the deterministic ``result_hash``, and
it never silently changes a scheduling decision.

This is a certification/trust layer only â€” it computes nothing on its own and
makes no trading, signalling, or prediction decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: Default dataset-size thresholds (number of observations) separating the
#: SMALL / MEDIUM / LARGE classes.  Configurable per profile.
DEFAULT_SIZE_THRESHOLDS: tuple[int, int] = (1_000, 10_000)

#: Initial scheduler policy version (bumped when the decision rule changes).
POLICY_VERSION = "1.0.0"


class DatasetSizeClass(str, Enum):
    """Deterministic bucket of a dataset's length."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class OperationComplexity(str, Enum):
    """Static complexity class of a ``QuantComputationInterface`` operation.

    Used for diagnostics and for seeding the certified performance profile
    before measured data exists.  It is a coarse, stable classification, not a
    benchmark.
    """

    LIGHT = "light"  # single pass, element-wise (e.g. returns)
    STANDARD = "standard"  # one or two passes over the series
    HEAVY = "heavy"  # multi-pass / composed aggregate (e.g. simulation)


#: Stable per-operation complexity classification.
OPERATION_COMPLEXITY: dict[str, OperationComplexity] = {
    "calculate_returns": OperationComplexity.LIGHT,
    "calculate_volatility": OperationComplexity.STANDARD,
    "calculate_drawdown": OperationComplexity.STANDARD,
    "calculate_statistics": OperationComplexity.STANDARD,
    "calculate_metrics": OperationComplexity.HEAVY,
    "calculate_performance_analytics": OperationComplexity.STANDARD,
    "run_simulation": OperationComplexity.HEAVY,
}


def classify_size(n: int | None, thresholds: Sequence[int] = DEFAULT_SIZE_THRESHOLDS) -> DatasetSizeClass:
    """Bucket a dataset length into a deterministic size class.

    ``None`` (unknown length) maps to SMALL.  ``thresholds`` is an ascending
    sequence; lengths <= t0 are SMALL, <= t1 are MEDIUM, above are LARGE.
    """
    if n is None:
        return DatasetSizeClass.SMALL
    count = int(n)
    if count <= int(thresholds[0]):
        return DatasetSizeClass.SMALL
    if count <= int(thresholds[1]):
        return DatasetSizeClass.MEDIUM
    return DatasetSizeClass.LARGE


def operation_complexity(operation: str) -> OperationComplexity:
    """Return the static complexity class for ``operation``."""
    return OPERATION_COMPLEXITY.get(operation, OperationComplexity.STANDARD)


def _estimate_dataset_size(inputs: Mapping[str, Any]) -> int | None:
    """Estimate the dataset length from a raw ``execute`` inputs mapping.

    Only ``inputs`` values are inspected (the request payload).  The first
    usable sequence-like or sized value wins; structured inputs without a
    meaningful length return None (â†’ SMALL).  This is a heuristic for
    scheduling only â€” the backends remain the authority on data parsing.
    """
    for value in inputs.values():
        if isinstance(value, (list, tuple)):
            if value and isinstance(value[0], (int, float)):
                return len(value)
            return None
        if hasattr(value, "prices"):
            try:
                return len(value.prices)
            except Exception:
                pass
        if hasattr(value, "__len__"):
            try:
                length = len(value)
            except Exception:
                continue
            if isinstance(length, int) and 0 <= length <= 10_000_000:
                return length
    return None


def estimate_dataset_size(inputs: Mapping[str, Any]) -> int | None:
    """Public estimate of a dataset's length for scheduling diagnostics."""
    return _estimate_dataset_size(inputs)


@dataclass(frozen=True)
class PerformanceStat:
    """Immutable runtime statistic for one (backend, operation, size-class).

    Attributes:
        mean_ms: Arithmetic mean observed wall-clock duration (milliseconds).
        count: Number of observations.
        last_ms: Most recent observation (milliseconds).
    """

    mean_ms: float
    count: int = 1
    last_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_ms": round(float(self.mean_ms), 6),
            "count": int(self.count),
            "last_ms": round(float(self.last_ms), 6),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PerformanceStat:
        return cls(
            mean_ms=float(data["mean_ms"]),
            count=int(data.get("count", 1)),
            last_ms=float(data.get("last_ms", 0.0)),
        )

    @classmethod
    def from_measurement(cls, elapsed_ms: float) -> PerformanceStat:
        return cls(mean_ms=float(elapsed_ms), count=1, last_ms=float(elapsed_ms))


@dataclass(frozen=True)
class SchedulerDecision:
    """Immutable record of one scheduling decision.

    Attributes:
        selected_backend: Backend identifier chosen (or None for reference).
        rationale: Human-readable reason for the choice.
        policy_version: Version of the decision rule.
        profile_version: Version of the certified performance profile used
            ("" when no profile was consulted).
        candidates_considered: Ordered capability names of the candidates the
            scheduler considered.
        rejected_reasons: Ordered ``(backend_name, reason)`` pairs for
            candidates that were NOT selected.
    """

    selected_backend: str | None
    rationale: str
    policy_version: str = POLICY_VERSION
    profile_version: str = ""
    candidates_considered: tuple[str, ...] = ()
    rejected_reasons: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_backend": self.selected_backend,
            "rationale": self.rationale,
            "policy_version": self.policy_version,
            "profile_version": self.profile_version,
            "candidates_considered": list(self.candidates_considered),
            "rejected_reasons": [[name, reason] for name, reason in self.rejected_reasons],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SchedulerDecision:
        rejected = [
            tuple(pair)  # type: ignore[arg-type]
            for pair in data.get("rejected_reasons", [])
        ]
        return cls(
            selected_backend=data.get("selected_backend"),
            rationale=str(data.get("rationale", "")),
            policy_version=str(data.get("policy_version", POLICY_VERSION)),
            profile_version=str(data.get("profile_version", "")),
            candidates_considered=tuple(data.get("candidates_considered", ())),
            rejected_reasons=tuple(rejected),
        )


class CertifiedPerformanceProfile:
    """Versioned table of measured runtimes used for deterministic selection.

    The profile maps ``(backend_name, operation, size_class)`` to a
    ``PerformanceStat``.  It is seeded from the official benchmark
    (``from_benchmark``) or from explicit measurements, and is read-only for
    scheduling.  ``recalibrate`` is the explicit, auditable way to incorporate
    historical telemetry: it returns a NEW profile with a bumped version, so a
    router instance's decisions stay reproducible per version.
    """

    _KEY = tuple[str, str, str]

    def __init__(
        self,
        measurements: Mapping[tuple[str, str, Any], PerformanceStat] | None = None,
        thresholds: Sequence[int] = DEFAULT_SIZE_THRESHOLDS,
        version: str = "0",
        source: str = "",
    ) -> None:
        self._stats: dict[tuple[str, str, str], PerformanceStat] = {
            (
                str(backend),
                str(op),
                size.value if isinstance(size, DatasetSizeClass) else str(size),
            ): stat
            for (backend, op, size), stat in (measurements or {}).items()
        }
        self._thresholds: tuple[int, int] = (
            int(thresholds[0]),
            int(thresholds[1]),
        )
        self.version: str = version
        self.source: str = source

    @property
    def thresholds(self) -> tuple[int, int]:
        """The dataset-size thresholds used for classification."""
        return self._thresholds

    def estimate_ms(self, backend: str, operation: str, size: DatasetSizeClass) -> float | None:
        """Return the mean runtime estimate (ms) or None when unmeasured."""
        stat = self._stats.get((str(backend), str(operation), size.value))
        return stat.mean_ms if stat is not None else None

    def faster_than(self, operation: str, size: DatasetSizeClass, a: str, b: str) -> bool:
        """True when backend ``a``'s estimate is strictly faster than ``b``'s.

        Returns False when either estimate is unmeasured (unknown is never
        assumed faster).
        """
        ea = self.estimate_ms(a, operation, size)
        eb = self.estimate_ms(b, operation, size)
        if ea is None or eb is None:
            return False
        return ea < eb

    def measured(self) -> int:
        """Number of measured (backend, operation, size) entries."""
        return len(self._stats)

    def add(
        self,
        backend: str,
        operation: str,
        size: DatasetSizeClass,
        stat: PerformanceStat,
    ) -> CertifiedPerformanceProfile:
        """Return a new profile with ``(backend, operation, size)`` updated."""
        new = CertifiedPerformanceProfile(
            measurements=self._stats,
            thresholds=self._thresholds,
            version=self.version,
            source=self.source,
        )
        new._stats[(str(backend), str(operation), size.value)] = stat
        return new

    def recalibrate(
        self,
        history: ExecutionHistory,
        version: str | None = None,
    ) -> CertifiedPerformanceProfile:
        """Return a NEW profile recalibrated from observed telemetry.

        The new profile version is ``<old>.<n>`` (or an explicit ``version``).
        This is the only sanctioned way historical performance influences
        selection â€” an explicit, versioned action.

        Args:
            history: The execution history to learn from.
            version: Optional explicit new version string.
        """
        samples_by_key: dict[tuple[str, str, str], list[float]] = {}
        for record in history.records:
            if record.size_class is None or record.backend is None:
                continue
            key = (record.backend, record.operation, str(record.size_class))
            samples_by_key.setdefault(key, []).append(record.duration_ms)

        merged = dict(self._stats)
        for key, samples in samples_by_key.items():
            if not samples:
                continue
            prior = merged.get(key)
            if prior is not None:
                total = prior.mean_ms * prior.count + sum(samples)
                count = prior.count + len(samples)
                merged[key] = PerformanceStat(
                    mean_ms=total / count,
                    count=count,
                    last_ms=samples[-1],
                )
            else:
                merged[key] = PerformanceStat.from_measurement(sum(samples) / len(samples))

        new_version = version or f"{self.version}.1"
        return CertifiedPerformanceProfile(
            measurements=merged,
            thresholds=self._thresholds,
            version=new_version,
            source=self.source or "recalibrated-from-history",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "thresholds": list(self._thresholds),
            "measurements": {f"{backend}|{operation}|{size}": stat.to_dict() for (backend, operation, size), stat in sorted(self._stats.items())},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CertifiedPerformanceProfile:
        measurements: dict[tuple[str, str, DatasetSizeClass], PerformanceStat] = {}
        for key, stat in data.get("measurements", {}).items():
            parts = str(key).split("|")
            if len(parts) != 3:
                continue
            backend, operation, size = parts
            try:
                size_class = DatasetSizeClass(size)
            except ValueError:
                continue
            measurements[(backend, operation, size_class.value)] = PerformanceStat.from_dict(stat)
        return cls(
            measurements=measurements,
            thresholds=data.get("thresholds", DEFAULT_SIZE_THRESHOLDS),
            version=str(data.get("version", "0")),
            source=str(data.get("source", "")),
        )

    @classmethod
    def from_benchmark(
        cls,
        benchmark_rows: Sequence[Mapping[str, Any]],
        backend_name: str,
        reference_backend_name: str,
        version: str = "1.0.0",
    ) -> CertifiedPerformanceProfile:
        """Build a profile from ``benchmark_cpp.run_benchmark()`` row dicts.

        Each row is ``{"operation": str, "measurements": [{"size", "python_s",
        "cpp_s", "speedup"}]}``.  Both the accelerated backend and the Python
        reference backend are recorded so the scheduler can compare
        estimates deterministically.
        """
        measurements: dict[tuple[str, str, DatasetSizeClass], PerformanceStat] = {}
        for row in benchmark_rows:
            operation = str(row["operation"])
            for m in row.get("measurements", []):
                size_class = classify_size(int(m["size"]))
                measurements[(backend_name, operation, size_class)] = PerformanceStat.from_measurement(float(m["cpp_s"]) * 1000.0)
                measurements[(reference_backend_name, operation, size_class)] = PerformanceStat.from_measurement(float(m["python_s"]) * 1000.0)
        return cls(
            measurements=measurements,
            version=version,
            source=f"benchmark:{backend_name}",
        )


@dataclass(frozen=True)
class ExecutionRecord:
    """One observational telemetry record from a router execution.

    All fields are observational â€” none participate in the deterministic
    ``result_hash``.

    Attributes:
        operation: Operation executed.
        backend: Backend that produced the returned output.
        size_class: Dataset size class at execution time (or None).
        duration_ms: Observed wall-clock duration (milliseconds).
        validation_status: ``"passed"`` / ``"failed"`` / ``"not_required"``.
        error_code: Stable error code of the outcome.
        fallback_count: Number of candidate attempts that did not produce the
            final output.
    """

    operation: str
    backend: str | None
    size_class: str | None
    duration_ms: float
    validation_status: str
    error_code: str
    fallback_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "backend": self.backend,
            "size_class": self.size_class,
            "duration_ms": round(float(self.duration_ms), 6),
            "validation_status": self.validation_status,
            "error_code": self.error_code,
            "fallback_count": int(self.fallback_count),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionRecord:
        return cls(
            operation=str(data["operation"]),
            backend=data.get("backend"),
            size_class=data.get("size_class"),
            duration_ms=float(data.get("duration_ms", 0.0)),
            validation_status=str(data.get("validation_status", "")),
            error_code=str(data.get("error_code", "")),
            fallback_count=int(data.get("fallback_count", 0)),
        )


@dataclass
class ExecutionHistory:
    """Observational log of router executions (never hashed).

    Records are appended in execution order.  ``summary`` aggregates the log
    into a deterministic, JSON-compatible report for observability tooling.
    """

    records: list[ExecutionRecord] = field(default_factory=list)

    def record(self, entry: ExecutionRecord) -> None:
        self.records.append(entry)

    def __len__(self) -> int:
        return len(self.records)

    def summary(self) -> dict[str, Any]:
        """Deterministic aggregate over all records."""
        by_backend: dict[str, int] = {}
        by_op: dict[str, int] = {}
        total_ms = 0.0
        fallback_count = 0
        for r in self.records:
            by_backend[r.backend or "unknown"] = by_backend.get(r.backend or "unknown", 0) + 1
            by_op[r.operation] = by_op.get(r.operation, 0) + 1
            total_ms += r.duration_ms
            fallback_count += r.fallback_count
        return {
            "total_executions": len(self.records),
            "total_fallbacks": fallback_count,
            "total_duration_ms": round(total_ms, 6),
            "executions_per_backend": dict(sorted(by_backend.items())),
            "executions_per_operation": dict(sorted(by_op.items())),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.to_dict() for r in self.records]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionHistory:
        return cls(records=[ExecutionRecord.from_dict(r) for r in data.get("records", [])])


class BackendScheduler:
    """Deterministic, profile-driven candidate selection.

    ``decide`` is a pure function of its arguments: identical
    (operation, inputs, eligible candidates, profile) â†’ identical decision.
    When no profile is set, it reproduces the Phase 4.1 behavior (first
    registered candidate wins).
    """

    def __init__(
        self,
        profile: CertifiedPerformanceProfile | None = None,
        policy_version: str = POLICY_VERSION,
    ) -> None:
        self._profile = profile
        self.policy_version = policy_version

    @property
    def profile(self) -> CertifiedPerformanceProfile | None:
        return self._profile

    def set_profile(self, profile: CertifiedPerformanceProfile | None) -> None:
        """Install (or clear) the certified performance profile.

        The profile is configuration: identical inputs + identical profile â†’
        identical scheduling decisions.
        """
        if profile is not None and not isinstance(profile, CertifiedPerformanceProfile):
            raise TypeError("profile must be a CertifiedPerformanceProfile or None")
        self._profile = profile

    @property
    def profile_version(self) -> str:
        return self._profile.version if self._profile is not None else ""

    def decide(
        self,
        operation: str,
        inputs: Mapping[str, Any],
        eligible: Sequence[tuple[str, Any]],
    ) -> SchedulerDecision:
        """Select the backend for ``operation`` given the eligible candidates.

        Args:
            operation: The operation to schedule.
            inputs: The raw execution inputs mapping (used only to estimate
                dataset size).
            eligible: Ordered ``(backend_name, backend)`` pairs that already
                passed the capability check and trust boundary (in
                registration order).

        Returns:
            A frozen ``SchedulerDecision``.
        """
        if not eligible:
            return SchedulerDecision(
                selected_backend=None,
                rationale="no eligible candidate; reference backend will run",
                policy_version=self.policy_version,
                profile_version=self.profile_version,
            )

        size = classify_size(
            _estimate_dataset_size(inputs),
            self._profile.thresholds if self._profile is not None else DEFAULT_SIZE_THRESHOLDS,
        )

        # Without a profile, reproduce first-registered-candidate selection.
        if self._profile is None:
            first = eligible[0][0]
            return SchedulerDecision(
                selected_backend=first,
                rationale=(f"no certified performance profile; first eligible candidate selected ({size.value} dataset)"),
                policy_version=self.policy_version,
                profile_version="",
                candidates_considered=tuple(name for name, _ in eligible),
            )

        estimates = [(name, self._profile.estimate_ms(name, operation, size)) for name, _ in eligible]
        measured = [(name, est) for name, est in estimates if est is not None]

        if not measured:
            # No measurements for this (op, size) â€” fall back to deterministic
            # registration order (never assume unknown speed).
            first = eligible[0][0]
            return SchedulerDecision(
                selected_backend=first,
                rationale=(f"no profile measurements for {operation} at {size.value}; selected first eligible candidate ({first})"),
                policy_version=self.policy_version,
                profile_version=self.profile_version,
                candidates_considered=tuple(name for name, _ in eligible),
            )

        measured.sort(key=lambda item: (item[1], item[0]))
        best = measured[0][0]
        rejected = [(name, f"estimated slower ({est:.3f}ms vs {measured[0][1]:.3f}ms)") for name, est in measured[1:]]
        return SchedulerDecision(
            selected_backend=best,
            rationale=(f"certified performance profile chose {best} for {operation} at {size.value} dataset size"),
            policy_version=self.policy_version,
            profile_version=self.profile_version,
            candidates_considered=tuple(name for name, _ in eligible),
            rejected_reasons=tuple(rejected),
        )


__all__ = [
    "POLICY_VERSION",
    "DEFAULT_SIZE_THRESHOLDS",
    "DatasetSizeClass",
    "OperationComplexity",
    "OPERATION_COMPLEXITY",
    "classify_size",
    "operation_complexity",
    "estimate_dataset_size",
    "PerformanceStat",
    "SchedulerDecision",
    "CertifiedPerformanceProfile",
    "ExecutionRecord",
    "ExecutionHistory",
    "BackendScheduler",
]
