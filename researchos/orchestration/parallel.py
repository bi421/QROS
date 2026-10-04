"""Parallel research orchestration primitives.

Adds parallel execution to the existing orchestration layer without creating
a second scientific core, runner, repository, or evidence model.

Execution is deterministic in waves:

    immutable input snapshot
        |
        +---- branch A ----+
        +---- branch B ----+---- barrier ---- next wave
        +---- branch C ----+

Branches in one wave must be independent. Results are returned in declared
plan order, never completion order. Any branch failure fails the whole wave
and prevents later waves from starting.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class ParallelOrchestrationError(RuntimeError):
    """Raised when a parallel research wave cannot complete safely."""


@dataclass(frozen=True)
class ResearchBranch(Generic[T]):
    """One independent unit of research work."""

    branch_id: str
    run: Callable[[Mapping[str, Any]], T]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.branch_id, str) or not self.branch_id.strip():
            raise ValueError("branch_id must be a non-empty string")
        object.__setattr__(self, "branch_id", self.branch_id.strip())
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchWave:
    """A set of branches that may execute concurrently."""

    wave_id: str
    branches: tuple[ResearchBranch[Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.wave_id, str) or not self.wave_id.strip():
            raise ValueError("wave_id must be a non-empty string")
        object.__setattr__(self, "wave_id", self.wave_id.strip())
        if not self.branches:
            raise ValueError("a research wave must contain at least one branch")
        ids = [branch.branch_id for branch in self.branches]
        if len(ids) != len(set(ids)):
            raise ValueError("branch_id values must be unique inside a wave")


@dataclass(frozen=True)
class ParallelBranchResult(Generic[T]):
    """Immutable result for one branch."""

    branch_id: str
    value: T


@dataclass(frozen=True)
class ParallelResearchResult:
    """Immutable result of all completed waves."""

    waves: tuple[tuple[ParallelBranchResult[Any], ...], ...]

    def by_branch_id(self) -> dict[str, Any]:
        """Return a deterministic branch-id -> value mapping."""
        result: dict[str, Any] = {}
        for wave in self.waves:
            for branch in wave:
                if branch.branch_id in result:
                    raise ParallelOrchestrationError(
                        f"duplicate branch result: {branch.branch_id}"
                    )
                result[branch.branch_id] = branch.value
        return result


class ParallelResearchExecutor:
    """Execute independent branches concurrently in dependency waves."""

    def __init__(
        self,
        *,
        max_workers: int | None = None,
        executor_factory: Callable[[int | None], Executor] | None = None,
    ) -> None:
        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = max_workers
        self._executor_factory = executor_factory or self._default_executor

    def _default_executor(self, max_workers: int | None) -> Executor:
        return ThreadPoolExecutor(max_workers=max_workers)

    def run(
        self,
        waves: Sequence[ResearchWave],
        context: Mapping[str, Any] | None = None,
    ) -> ParallelResearchResult:
        """Run waves left-to-right; branches inside a wave run concurrently.

        The input context is snapshotted before dispatch. Results are collected
        in declared branch order, making output deterministic even when branch
        completion order differs.

        Any branch failure cancels work that has not started, raises a single
        orchestration error, and prevents all later waves from starting.
        """
        if not waves:
            raise ValueError("at least one research wave is required")

        snapshot = dict(context or {})
        completed: list[tuple[ParallelBranchResult[Any], ...]] = []

        for wave in waves:
            executor = self._executor_factory(self._max_workers)
            futures: list[Future[Any]] = []
            try:
                futures = [
                    executor.submit(branch.run, snapshot)
                    for branch in wave.branches
                ]
                values: list[Any] = []
                failures: list[tuple[str, BaseException]] = []

                for branch, future in zip(wave.branches, futures, strict=True):
                    try:
                        values.append(future.result())
                    except BaseException as exc:
                        failures.append((branch.branch_id, exc))

                if failures:
                    for future in futures:
                        future.cancel()
                    details = "; ".join(
                        f"{branch_id}: {type(exc).__name__}: {exc}"
                        for branch_id, exc in failures
                    )
                    raise ParallelOrchestrationError(
                        f"wave {wave.wave_id!r} failed; no later wave may run: {details}"
                    )

                completed.append(
                    tuple(
                        ParallelBranchResult(branch_id=branch.branch_id, value=value)
                        for branch, value in zip(wave.branches, values, strict=True)
                    )
                )
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

        return ParallelResearchResult(waves=tuple(completed))


__all__ = [
    "ParallelOrchestrationError",
    "ResearchBranch",
    "ResearchWave",
    "ParallelBranchResult",
    "ParallelResearchResult",
    "ParallelResearchExecutor",
]
