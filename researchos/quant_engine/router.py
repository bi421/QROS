"""
BackendRouter — trust-boundary routing for computation backends.

Phase 4.1: backend certification and trust-boundary hardening.
Phase 4.2: structured validation + execution audit metadata.
Phase 4.4: intelligent backend scheduling & production hardening.

The router enforces the certified execution flow::

    Request
      ↓
    Capability check
      ↓
    Scheduler (Phase 4.4) → candidate backend
      ↓
    Validation (against the Python reference backend)
      ↓
    Success → Return
      ↓ (else) next candidate
    Automatic Python reference fallback

The Python reference backend (``PythonQuantBackend``) remains the ONLY
scientific source of truth: candidate outputs are always validated against
it, and any candidate that fails capability, execution, or numerical
validation is replaced by the reference backend's output.

Every execution produces an immutable ``BackendExecutionMetadata`` record
(backend, version, fallback_used, validation_status, execution_time_ms,
result_hash, error_code, execution_timestamp, capability_profile, and, when a
scheduler is configured, ``scheduler_decision``, ``policy_version``,
``profile_version``, ``fallback_count``, ``attempted_backends``).
``result_hash`` is the deterministic canonical SHA-256 digest of the execution
(see ``backend_hash``); ``execution_time_ms`` and ``execution_timestamp`` are
observational timing that are intentionally NOT part of the hash.

When a ``BackendScheduler`` is installed (Phase 4.4), candidate selection is a
pure, deterministic function of (operation, inputs, eligible candidates,
certified performance profile).  The Python reference is also a schedulable
option (selected deliberately when its certified estimate is cheapest), so the
per-operation accelerated-backend adoption policy is realized mechanically
rather than as a failure-driven fallback.  Every execution appends an
observational ``ExecutionRecord`` to ``router.history``.

This is a certification/trust layer only — it computes nothing on its own and
makes no trading, signalling, or prediction decisions.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from researchos.quant_engine.backend import PythonQuantBackend
from researchos.quant_engine.backend_hash import (
    compute_backend_result_hash,
    compute_input_hash,
)
from researchos.quant_engine.capabilities import BackendCapabilities
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.numerical_validation import (
    NumericalComparator,
    NumericalComparisonError,
    NumericalValidationResult,
    ValidationStatus,
)
from researchos.quant_engine.scheduler import (
    DEFAULT_SIZE_THRESHOLDS,
    BackendScheduler,
    CertifiedPerformanceProfile,
    ExecutionHistory,
    ExecutionRecord,
    SchedulerDecision,
    _estimate_dataset_size,
    classify_size,
)

#: Stable error codes recorded in ``BackendExecutionMetadata.error_code``.
ERROR_OK = "ok"
ERROR_NO_CANDIDATE = "unavailable"
ERROR_EXECUTION_FAILED = "execution_failed"
ERROR_VALIDATION_FAILED = "validation_failed"
ERROR_CAPABILITY_MISSING = "capability_missing"
ERROR_TRUST_BOUNDARY = "trust_boundary_violation"

#: Supported ``validation`` modes for ``execute``.
_VALIDATION_MODES = ("auto", "numeric", "structural")


class BackendRouterError(Exception):
    """Base class for all BackendRouter errors."""


class BackendCapabilityError(BackendRouterError):
    """Raised when a backend advertises capabilities that violate the
    ResearchOS compute contract."""


class BackendValidationError(BackendRouterError):
    """Raised when a backend output fails numerical validation."""


class BackendExecutionError(BackendRouterError):
    """Raised when a backend cannot execute a requested operation."""


@dataclass(frozen=True)
class BackendExecutionMetadata:
    """Immutable audit record for one router execution.

    Attributes:
        operation: Operation name that was executed.
        backend: Backend identifier that produced the returned output.
        version: Backend version that produced the returned output.
        fallback_used: Whether the Python reference backend was used.
        validation_status: ``"passed"`` / ``"failed"`` / ``"not_required"``.
        execution_time_ms: Wall-clock time of the execution (observational).
        result_hash: Deterministic canonical SHA-256 of the execution.
        error_code: Stable error code describing the outcome.
        execution_timestamp: ISO-8601 wall-clock timestamp (observational).
        capability_profile: Capability declaration of the producing backend.
        scheduler_decision: The Phase 4.4 scheduling decision (or None).
        policy_version: Scheduler policy version ("" when no scheduler).
        profile_version: Certified profile version ("" when none).
        fallback_count: Number of candidate attempts that did not produce
            the final output.
        attempted_backends: Ordered backend names that were attempted and
            did not produce the final output.
    """

    operation: str
    backend: str
    version: str
    fallback_used: bool
    validation_status: str
    execution_time_ms: float
    result_hash: str
    error_code: str
    execution_timestamp: str = ""
    capability_profile: BackendCapabilities | None = None
    scheduler_decision: SchedulerDecision | None = None
    policy_version: str = ""
    profile_version: str = ""
    fallback_count: int = 0
    attempted_backends: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-compatible mapping."""
        return {
            "operation": self.operation,
            "backend": self.backend,
            "version": self.version,
            "fallback_used": self.fallback_used,
            "validation_status": self.validation_status,
            "execution_time_ms": round(float(self.execution_time_ms), 6),
            "result_hash": self.result_hash,
            "error_code": self.error_code,
            "execution_timestamp": self.execution_timestamp,
            "capability_profile": (self.capability_profile.to_dict() if self.capability_profile is not None else None),
            "scheduler_decision": (self.scheduler_decision.to_dict() if self.scheduler_decision is not None else None),
            "policy_version": self.policy_version,
            "profile_version": self.profile_version,
            "fallback_count": self.fallback_count,
            "attempted_backends": list(self.attempted_backends),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BackendExecutionMetadata:
        """Reconstruct from a ``to_dict()`` mapping."""
        caps = data.get("capability_profile")
        if caps is not None:
            caps = BackendCapabilities.from_dict(caps)
        decision = data.get("scheduler_decision")
        if decision is not None:
            decision = SchedulerDecision.from_dict(decision)
        return cls(
            operation=str(data["operation"]),
            backend=str(data["backend"]),
            version=str(data["version"]),
            fallback_used=bool(data["fallback_used"]),
            validation_status=str(data["validation_status"]),
            execution_time_ms=float(data["execution_time_ms"]),
            result_hash=str(data["result_hash"]),
            error_code=str(data["error_code"]),
            execution_timestamp=str(data.get("execution_timestamp", "")),
            capability_profile=caps,
            scheduler_decision=decision,
            policy_version=str(data.get("policy_version", "")),
            profile_version=str(data.get("profile_version", "")),
            fallback_count=int(data.get("fallback_count", 0)),
            attempted_backends=tuple(data.get("attempted_backends", ())),
        )


@dataclass(frozen=True)
class BackendExecutionResult:
    """Frozen result of one router execution: audit metadata + output.

    Attributes:
        metadata: Immutable ``BackendExecutionMetadata``.
        output: The returned backend output.
    """

    metadata: BackendExecutionMetadata
    output: Any


class BackendRouter:
    """Certification router that enforces the trust-boundary execution flow.

    The router is free of global state: every instance is fully independent.
    It is deterministic — for identical candidates, reference, request, and
    timings-independent inputs, the returned output and ``result_hash`` are
    identical.

    When a ``BackendScheduler`` is installed (Phase 4.4), candidate selection
    is a pure function of (operation, inputs, eligible candidates, profile),
    and every execution is recorded in ``history`` observationally.
    """

    def __init__(
        self,
        reference_backend: QuantComputationInterface | None = None,
        candidates: list[QuantComputationInterface] | None = None,
        scheduler: BackendScheduler | None = None,
        history: ExecutionHistory | None = None,
    ) -> None:
        self._reference = reference_backend or PythonQuantBackend()
        if not isinstance(self._reference, QuantComputationInterface):
            raise TypeError("reference_backend must implement QuantComputationInterface")
        self._candidates: list[QuantComputationInterface] = list(candidates or [])
        if scheduler is not None and not isinstance(scheduler, BackendScheduler):
            raise TypeError("scheduler must be a BackendScheduler or None")
        self._scheduler = scheduler
        self._history = history if history is not None else ExecutionHistory()

    # ── configuration ────────────────────────────────────────────────────

    @property
    def reference_backend(self) -> QuantComputationInterface:
        """The certified Python reference backend (source of truth)."""
        return self._reference

    def set_reference(self, backend: QuantComputationInterface) -> None:
        """Replace the reference backend used for validation."""
        if not isinstance(backend, QuantComputationInterface):
            raise TypeError("reference backend must implement QuantComputationInterface")
        self._reference = backend

    def register(self, backend: QuantComputationInterface) -> None:
        """Register a candidate backend eligible for routing.

        Raises:
            TypeError: If ``backend`` does not implement
                ``QuantComputationInterface``.
        """
        if not isinstance(backend, QuantComputationInterface):
            raise TypeError("candidate backend must implement QuantComputationInterface")
        if backend in self._candidates:
            return
        self._candidates.append(backend)

    def list_candidates(self) -> tuple[BackendCapabilities, ...]:
        """Return the capability declarations of all registered candidates."""
        out: list[BackendCapabilities] = []
        for backend in self._candidates:
            caps = self._safe_capabilities(backend)
            if caps is not None:
                out.append(caps)
        return tuple(out)

    # ── Phase 4.4 scheduler configuration ────────────────────────────────

    @property
    def scheduler(self) -> BackendScheduler | None:
        """The installed scheduler (or None)."""
        return self._scheduler

    @property
    def history(self) -> ExecutionHistory:
        """Observational execution history (never hashed)."""
        return self._history

    def set_scheduler(self, scheduler: BackendScheduler | None) -> None:
        """Install (or clear) the scheduler used for candidate selection."""
        if scheduler is not None and not isinstance(scheduler, BackendScheduler):
            raise TypeError("scheduler must be a BackendScheduler or None")
        self._scheduler = scheduler

    def set_scheduler_profile(self, profile: CertifiedPerformanceProfile | None) -> None:
        """Install (or clear) the scheduler's certified performance profile."""
        if self._scheduler is None:
            if profile is None:
                return
            self._scheduler = BackendScheduler()
        self._scheduler.set_profile(profile)

    @property
    def scheduler_profile(self) -> CertifiedPerformanceProfile | None:
        """The scheduler's current certified performance profile (or None)."""
        return self._scheduler.profile if self._scheduler is not None else None

    def recalibrate_profile(self, version: str | None = None) -> CertifiedPerformanceProfile | None:
        """Fold observed execution history into a NEW versioned profile.

        This is the explicit, auditable way historical performance enters
        scheduling.  Returns the new profile (and installs it on the
        scheduler), or None when no scheduler is installed.
        """
        if self._scheduler is None:
            self._scheduler = BackendScheduler()
        current = self._scheduler.profile
        if current is None:
            current = CertifiedPerformanceProfile(version="0", source="router")
        new_profile = current.recalibrate(self._history, version=version)
        self._scheduler.set_profile(new_profile)
        return new_profile

    # ── execution ────────────────────────────────────────────────────────

    def execute(
        self,
        operation: str,
        inputs: Mapping[str, Any],
        expected: Any = None,
        atol: float = NumericalComparator.DEFAULT_ATOL,
        rtol: float = NumericalComparator.DEFAULT_RTOL,
        validation: str = "auto",
    ) -> BackendExecutionResult:
        """Execute ``operation`` through the certified routing flow.

        Args:
            operation: Operation name exposed by ``QuantComputationInterface``.
            inputs: Mapping of keyword arguments for the operation.
            expected: Optional expected/reference output.  When ``None``, the
                reference backend is executed to produce the reference output.
            atol: Absolute tolerance for numerical validation.
            rtol: Relative tolerance for numerical validation.
            validation: Validation strategy — ``"auto"`` (choose numeric vs
                structural based on output shape), ``"numeric"`` (always
                numeric), or ``"structural"`` (always structural).

        Returns:
            A frozen ``BackendExecutionResult`` (metadata + output).

        Raises:
            BackendRouterError: If inputs are not a mapping or ``validation``
                is not a recognised mode.
            BackendExecutionError: If no backend (including the reference)
                can execute the operation.
        """
        if not isinstance(inputs, Mapping):
            raise BackendRouterError("inputs must be a mapping of keyword arguments")
        if validation not in _VALIDATION_MODES:
            raise BackendRouterError(f"validation must be one of {_VALIDATION_MODES}, got {validation!r}")

        comparator = NumericalComparator()
        input_hash = compute_input_hash(inputs)
        start = time.perf_counter()

        # ── 1. Candidate ordering (Phase 4.4 scheduler) ──────────────────
        eligible, trust_rejected = self._eligible_candidates(operation)
        decision = self._decide(operation, inputs, eligible)

        # If the scheduler deliberately selected the Python reference backend
        # (a schedulable option), run the reference directly and report it as
        # a deliberate (non-failure) reference execution.
        reference_name = self._reference_name()
        if decision is not None and decision.selected_backend == reference_name:
            return self._deliberate_reference(
                operation=operation,
                inputs=inputs,
                expected=expected,
                atol=atol,
                rtol=rtol,
                validation=validation,
                input_hash=input_hash,
                start=start,
                decision=decision,
            )

        # Build the ordered candidate attempt list: scheduler choice first,
        # then remaining eligible candidates in registration order.
        attempt_order = self._attempt_order(decision, eligible)
        attempted: list[str] = []
        fallback_count = 0
        last_error = ERROR_NO_CANDIDATE

        for candidate in attempt_order:
            caps = self._safe_capabilities(candidate)
            name = caps.backend_name if caps is not None else type(candidate).__name__
            version = caps.version if caps is not None else "unknown"

            # ── 2. Candidate execution ──────────────────────────────────
            try:
                output = self._invoke(candidate, operation, inputs)
            except Exception:  # candidate failed → next candidate
                attempted.append(name)
                fallback_count += 1
                last_error = ERROR_EXECUTION_FAILED
                continue

            # ── 3. Validation against the reference (source of truth) ────
            if expected is None:
                try:
                    expected = self._invoke(self._reference, operation, inputs)
                except Exception as exc:  # pragma: no cover - reference must work
                    raise BackendExecutionError(f"reference backend failed for {operation!r}: {exc}") from exc

            validation_result = self._validate(comparator, expected, output, atol=atol, rtol=rtol, mode=validation)
            if validation_result.passed:
                return self._success(
                    operation=operation,
                    name=name,
                    version=version,
                    caps=caps,
                    input_hash=input_hash,
                    output=output,
                    start=start,
                    decision=decision,
                    attempted=attempted,
                    fallback_count=fallback_count,
                    inputs=inputs,
                )

            attempted.append(name)
            fallback_count += 1
            last_error = ERROR_VALIDATION_FAILED

        # If no eligible candidate executed, but a candidate was rejected by
        # the trust boundary, report that as the reason.
        if not attempted and trust_rejected:
            last_error = ERROR_TRUST_BOUNDARY

        # ── 4. Automatic Python reference fallback ───────────────────────
        return self._fallback(
            operation=operation,
            inputs=inputs,
            expected=expected,
            atol=atol,
            rtol=rtol,
            validation=validation,
            input_hash=input_hash,
            start=start,
            tried_candidates=attempted,
            fallback_count=fallback_count,
            last_error=last_error,
            decision=decision,
        )

    def execute_planned(
        self,
        operation: str,
        inputs: Mapping[str, Any],
        required_backend: str,
        required_version: str,
        expected: Any = None,
        atol: float = NumericalComparator.DEFAULT_ATOL,
        rtol: float = NumericalComparator.DEFAULT_RTOL,
        validation: str = "auto",
    ) -> BackendExecutionResult:
        """Execute exactly the backend/version fixed by an immutable compute plan.

        Unlike normal router execution, this path never schedules, substitutes,
        or falls back to another backend.  A governed research plan therefore
        cannot silently execute a different computational route.
        """
        if not required_backend.strip() or not required_version.strip():
            raise BackendRouterError("planned execution requires backend and version")
        if not isinstance(inputs, Mapping):
            raise BackendRouterError("inputs must be a mapping of keyword arguments")
        if validation not in _VALIDATION_MODES:
            raise BackendRouterError(
                f"validation must be one of {_VALIDATION_MODES}, got {validation!r}"
            )

        target = None
        target_caps = None
        for candidate in [self._reference, *self._candidates]:
            caps = self._safe_capabilities(candidate)
            if caps is None:
                continue
            if caps.backend_name == required_backend and caps.version == required_version:
                target = candidate
                target_caps = caps
                break
        if target is None or target_caps is None:
            raise BackendExecutionError(
                f"planned backend unavailable: {required_backend}@{required_version}"
            )
        if not target_caps.supports(operation):
            raise BackendCapabilityError(
                f"planned backend does not support operation {operation!r}: "
                f"{required_backend}@{required_version}"
            )
        if not self._trust_boundary_ok(target_caps):
            raise BackendCapabilityError(
                f"planned backend violates the trust boundary: {required_backend}@{required_version}"
            )

        input_hash = compute_input_hash(inputs)
        start = time.perf_counter()
        try:
            output = self._invoke(target, operation, inputs)
        except Exception as exc:
            raise BackendExecutionError(
                f"planned backend failed for {operation!r}: {exc}"
            ) from exc

        validation_status = ValidationStatus.NOT_REQUIRED.value
        if expected is not None:
            validation_result = self._validate(
                NumericalComparator(), expected, output,
                atol=atol, rtol=rtol, mode=validation,
            )
            if not validation_result.passed:
                raise BackendValidationError(
                    f"planned backend output failed validation for {operation!r}"
                )
            validation_status = ValidationStatus.PASSED.value

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result_hash = compute_backend_result_hash(
            operation, target_caps.backend_name, target_caps.version, input_hash, output
        )
        metadata = self._build_metadata(
            operation=operation,
            backend=target_caps.backend_name,
            version=target_caps.version,
            fallback_used=False,
            validation_status=validation_status,
            execution_time_ms=elapsed_ms,
            result_hash=result_hash,
            error_code=ERROR_OK,
            caps=target_caps,
            decision=None,
            attempted=[],
            fallback_count=0,
        )
        self._record(
            operation, target_caps.backend_name, elapsed_ms,
            validation_status, ERROR_OK, 0, inputs,
        )
        return BackendExecutionResult(metadata=metadata, output=output)

    # ── internals ────────────────────────────────────────────────────────

    def _reference_name(self) -> str:
        caps = self._safe_capabilities(self._reference)
        return caps.backend_name if caps is not None else type(self._reference).__name__

    def _eligible_candidates(self, operation: str) -> tuple[list[tuple[str, QuantComputationInterface]], bool]:
        """Return ``(eligible, trust_rejected)``.

        ``eligible`` is the list of ``(name, backend)`` for all candidates
        that pass the capability check and trust boundary for ``operation``.
        ``trust_rejected`` is True when at least one registered candidate was
        ineligible specifically because it violated the trust boundary.
        """
        eligible: list[tuple[str, QuantComputationInterface]] = []
        trust_rejected = False
        for backend in self._candidates:
            caps = self._safe_capabilities(backend)
            if caps is None:
                continue
            if not caps.supports(operation):
                continue
            if not self._trust_boundary_ok(caps):
                trust_rejected = True
                continue
            eligible.append((caps.backend_name, backend))
        return eligible, trust_rejected

    def _decide(
        self,
        operation: str,
        inputs: Mapping[str, Any],
        eligible: Sequence[tuple[str, QuantComputationInterface]],
    ) -> SchedulerDecision | None:
        """Consult the scheduler (if any) for a candidate decision.

        When a scheduler is configured, the Python reference backend is also a
        schedulable option, so it is appended to the eligible set before
        consulting the scheduler.  Returns None when no scheduler is installed
        (Phase 4.1 behavior).
        """
        if self._scheduler is None:
            return None
        reference_name = self._reference_name()
        schedulable = list(eligible)
        # The reference backend is a schedulable option (per-operation
        # adoption policy).  It is placed last so it is only chosen when its
        # certified estimate is genuinely fastest.
        if not any(name == reference_name for name, _ in schedulable):
            schedulable.append((reference_name, self._reference))
        return self._scheduler.decide(operation, inputs, schedulable)

    def _attempt_order(
        self,
        decision: SchedulerDecision | None,
        eligible: Sequence[tuple[str, QuantComputationInterface]],
    ) -> list[QuantComputationInterface]:
        """Order the candidates to attempt for this execution.

        With a scheduler, the selected backend is attempted first, then the
        remaining eligible candidates in registration order.  Without a
        scheduler, all eligible candidates are attempted in registration
        order (Phase 4.1 behavior).
        """
        if not eligible:
            return []
        if decision is None or decision.selected_backend is None:
            return [b for _, b in eligible]

        selected = decision.selected_backend
        ordered: list[QuantComputationInterface] = []
        for name, backend in eligible:
            if name == selected:
                ordered.insert(0, backend)
            else:
                ordered.append(backend)
        return ordered

    def _validate(
        self,
        comparator: NumericalComparator,
        expected: Any,
        actual: Any,
        atol: float,
        rtol: float,
        mode: str = "auto",
    ) -> NumericalValidationResult:
        """Compare outputs using the requested validation mode.

        ``"auto"`` selects structural comparison for mapping outputs and
        numeric comparison otherwise (falling back to structural for
        structured objects).  ``"numeric"`` always uses numeric comparison
        (raising ``NumericalComparisonError`` for structured outputs).
        ``"structural"`` always uses structural comparison.
        """
        if mode == "numeric":
            return comparator.compare(expected, actual, atol=atol, rtol=rtol)
        if mode == "structural":
            return comparator.compare_structural(expected, actual, atol=atol, rtol=rtol)
        # auto: prefer numeric for simple numeric shapes; fall back to
        # structural for mapping or structured (to_dict) outputs.
        if isinstance(expected, Mapping) and isinstance(actual, Mapping):
            return comparator.compare_structural(expected, actual, atol=atol, rtol=rtol)
        try:
            return comparator.compare(expected, actual, atol=atol, rtol=rtol)
        except NumericalComparisonError:
            return comparator.compare_structural(expected, actual, atol=atol, rtol=rtol)

    def _success(
        self,
        *,
        operation: str,
        name: str,
        version: str,
        caps: BackendCapabilities | None,
        input_hash: str,
        output: Any,
        start: float,
        decision: SchedulerDecision | None,
        attempted: list[str],
        fallback_count: int,
        inputs: Mapping[str, Any] | None = None,
    ) -> BackendExecutionResult:
        """Record a successful candidate execution."""
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result_hash = compute_backend_result_hash(operation, name, version, input_hash, output)
        metadata = self._build_metadata(
            operation=operation,
            backend=name,
            version=version,
            fallback_used=False,
            validation_status=ValidationStatus.PASSED.value,
            execution_time_ms=elapsed_ms,
            result_hash=result_hash,
            error_code=ERROR_OK,
            caps=caps,
            decision=decision,
            attempted=attempted,
            fallback_count=fallback_count,
        )
        self._record(
            operation,
            name,
            elapsed_ms,
            ValidationStatus.PASSED.value,
            ERROR_OK,
            fallback_count,
            inputs,
        )
        return BackendExecutionResult(metadata=metadata, output=output)

    def _deliberate_reference(
        self,
        *,
        operation: str,
        inputs: Mapping[str, Any],
        expected: Any,
        atol: float,
        rtol: float,
        validation: str,
        input_hash: str,
        start: float,
        decision: SchedulerDecision,
    ) -> BackendExecutionResult:
        """Execute the operation on the reference backend as a deliberate
        scheduler choice (not a failure-driven fallback)."""
        output = self._invoke(self._reference, operation, inputs)
        caps = self._safe_capabilities(self._reference)
        name = self._reference_name()
        version = caps.version if caps is not None else "unknown"
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result_hash = compute_backend_result_hash(operation, name, version, input_hash, output)
        metadata = self._build_metadata(
            operation=operation,
            backend=name,
            version=version,
            fallback_used=True,
            validation_status=ValidationStatus.NOT_REQUIRED.value,
            execution_time_ms=elapsed_ms,
            result_hash=result_hash,
            error_code=ERROR_OK,
            caps=caps,
            decision=decision,
            attempted=[],
            fallback_count=0,
        )
        self._record(operation, name, elapsed_ms, ValidationStatus.NOT_REQUIRED.value, ERROR_OK, 0, inputs)
        return BackendExecutionResult(metadata=metadata, output=output)

    def _fallback(
        self,
        *,
        operation: str,
        inputs: Mapping[str, Any],
        expected: Any,
        atol: float,
        rtol: float,
        validation: str,
        input_hash: str,
        start: float,
        tried_candidates: list[str],
        fallback_count: int,
        last_error: str,
        decision: SchedulerDecision | None,
    ) -> BackendExecutionResult:
        """Execute the operation on the Python reference backend.

        The reference backend is the certified final fallback.  When a
        scheduler is configured, it is also a schedulable option (selected
        deliberately for per-operation adoption when fastest).
        """
        try:
            output = self._invoke(self._reference, operation, inputs)
        except Exception as exc:
            raise BackendExecutionError(f"no backend available for {operation!r}; reference failed: {exc}") from exc

        caps = self._safe_capabilities(self._reference)
        name = self._reference_name()
        version = caps.version if caps is not None else "unknown"

        validation_status = ValidationStatus.NOT_REQUIRED.value
        if expected is not None:
            validation_result = self._validate(
                NumericalComparator(),
                expected,
                output,
                atol=atol,
                rtol=rtol,
                mode=validation,
            )
            validation_status = validation_result.status.value

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result_hash = compute_backend_result_hash(operation, name, version, input_hash, output)
        metadata = self._build_metadata(
            operation=operation,
            backend=name,
            version=version,
            fallback_used=True,
            validation_status=validation_status,
            execution_time_ms=elapsed_ms,
            result_hash=result_hash,
            error_code=last_error,
            caps=caps,
            decision=decision,
            attempted=tried_candidates,
            fallback_count=fallback_count,
        )
        self._record(operation, name, elapsed_ms, validation_status, last_error, fallback_count, inputs)
        return BackendExecutionResult(metadata=metadata, output=output)

    def _build_metadata(
        self,
        *,
        operation: str,
        backend: str,
        version: str,
        fallback_used: bool,
        validation_status: str,
        execution_time_ms: float,
        result_hash: str,
        error_code: str,
        caps: BackendCapabilities | None,
        decision: SchedulerDecision | None,
        attempted: list[str],
        fallback_count: int,
    ) -> BackendExecutionMetadata:
        return BackendExecutionMetadata(
            operation=operation,
            backend=backend,
            version=version,
            fallback_used=fallback_used,
            validation_status=validation_status,
            execution_time_ms=execution_time_ms,
            result_hash=result_hash,
            error_code=error_code,
            execution_timestamp=datetime.now(timezone.utc).isoformat(),
            capability_profile=caps,
            scheduler_decision=decision,
            policy_version=decision.policy_version if decision is not None else "",
            profile_version=decision.profile_version if decision is not None else "",
            fallback_count=fallback_count,
            attempted_backends=tuple(attempted),
        )

    def _record(
        self,
        operation: str,
        backend: str,
        duration_ms: float,
        validation_status: str,
        error_code: str,
        fallback_count: int,
        inputs: Mapping[str, Any] | None = None,
    ) -> None:
        """Append an observational telemetry record to ``history``."""
        thresholds = self._scheduler.profile.thresholds if self._scheduler is not None and self._scheduler.profile is not None else DEFAULT_SIZE_THRESHOLDS
        size_class = classify_size(
            _estimate_dataset_size(inputs) if inputs is not None else None,
            thresholds,
        ).value
        record = ExecutionRecord(
            operation=operation,
            backend=backend,
            size_class=size_class,
            duration_ms=duration_ms,
            validation_status=validation_status,
            error_code=error_code,
            fallback_count=fallback_count,
        )
        self._history.record(record)

    @staticmethod
    def _safe_capabilities(backend: Any) -> BackendCapabilities | None:
        getter = getattr(backend, "capabilities", None)
        if not callable(getter):
            return None
        try:
            result = getter()
            return result if isinstance(result, BackendCapabilities) else None
        except Exception:
            return None

    @staticmethod
    def _trust_boundary_ok(caps: BackendCapabilities) -> bool:
        return all(
            (
                caps.deterministic,
                caps.stateless,
                caps.no_timestamps,
                caps.no_randomness,
                caps.explicit_typing,
            )
        )

    @staticmethod
    def _invoke(backend: Any, operation: str, inputs: Mapping[str, Any]) -> Any:
        fn = getattr(backend, operation, None)
        if not callable(fn):
            raise BackendExecutionError(f"backend {type(backend).__name__!r} has no callable {operation!r}")
        return fn(**dict(inputs))


def _validation_detail(validation: NumericalValidationResult) -> str:
    parts = []
    if not validation.shape_match:
        parts.append("shape mismatch")
    if validation.has_nan:
        parts.append("nan present")
    if validation.has_inf:
        parts.append("infinite value present")
    if not parts:
        parts.append(f"max_abs_error={validation.max_abs_error:.3e} max_rel_error={validation.max_rel_error:.3e}")
    return "; ".join(parts)


__all__ = [
    "ERROR_OK",
    "ERROR_NO_CANDIDATE",
    "ERROR_EXECUTION_FAILED",
    "ERROR_VALIDATION_FAILED",
    "ERROR_CAPABILITY_MISSING",
    "ERROR_TRUST_BOUNDARY",
    "BackendCapabilityError",
    "BackendExecutionError",
    "BackendExecutionMetadata",
    "BackendExecutionResult",
    "BackendRouter",
    "QuantBackendRouter",
    "BackendRouterError",
    "BackendValidationError",
]

# Backward compatibility alias
QuantBackendRouter = BackendRouter
