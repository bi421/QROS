"""Tests for deterministic parallel research orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Executor, Future
from typing import Any, TypeVar

import pytest

_T = TypeVar("_T")

from researchos.orchestration.parallel import (
    ParallelOrchestrationError,
    ParallelResearchExecutor,
    ResearchBranch,
    ResearchWave,
)


def test_branches_in_one_wave_execute_concurrently_and_preserve_plan_order() -> None:
    barrier = threading.Barrier(2)

    def branch_a(_context):
        barrier.wait(timeout=2)
        return "a"

    def branch_b(_context):
        barrier.wait(timeout=2)
        return "b"

    result = ParallelResearchExecutor(max_workers=2).run(
        (
            ResearchWave(
                wave_id="wave-1",
                branches=(
                    ResearchBranch("a", branch_a),
                    ResearchBranch("b", branch_b),
                ),
            ),
        ),
        {"snapshot": "immutable"},
    )

    assert [item.branch_id for item in result.waves[0]] == ["a", "b"]
    assert result.by_branch_id() == {"a": "a", "b": "b"}


def test_context_nested_containers_are_immutable() -> None:
    def branch(context):
        with pytest.raises(TypeError):
            context["nested"]["value"] = 2
        with pytest.raises(TypeError):
            context["values"][0] = "changed"
        with pytest.raises(AttributeError):
            context["flags"].add("changed")
        return (
            dict(context["nested"]),
            context["values"],
            context["flags"],
        )

    source = {
        "nested": {"value": 1},
        "values": ["a", "b"],
        "flags": {"x"},
    }

    result = ParallelResearchExecutor(max_workers=1).run(
        (ResearchWave("wave-1", (ResearchBranch("branch", branch),)),),
        source,
    )

    assert result.by_branch_id() == {
        "branch": (
            {"value": 1},
            ("a", "b"),
            frozenset({"x"}),
        )
    }
    assert source == {
        "nested": {"value": 1},
        "values": ["a", "b"],
        "flags": {"x"},
    }


def test_later_wave_waits_for_previous_wave() -> None:
    events: list[str] = []

    def first(_context):
        events.append("first")
        return 1

    def second(_context):
        assert events == ["first"]
        events.append("second")
        return 2

    result = ParallelResearchExecutor(max_workers=2).run(
        (
            ResearchWave("wave-1", (ResearchBranch("first", first),)),
            ResearchWave("wave-2", (ResearchBranch("second", second),)),
        )
    )

    assert result.by_branch_id() == {"first": 1, "second": 2}


def test_wave_failure_blocks_later_waves() -> None:
    later_started = False

    def fail(_context):
        raise ValueError("boom")

    def later(_context):
        nonlocal later_started
        later_started = True
        return "must-not-run"

    with pytest.raises(ParallelOrchestrationError, match="wave 'wave-1' failed"):
        ParallelResearchExecutor(max_workers=2).run(
            (
                ResearchWave("wave-1", (ResearchBranch("fail", fail),)),
                ResearchWave("wave-2", (ResearchBranch("later", later),)),
            )
        )

    assert later_started is False


def test_empty_plan_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one research wave"):
        ParallelResearchExecutor().run(())


def test_duplicate_branch_ids_across_waves_are_rejected_before_execution() -> None:
    started: list[str] = []

    def first(_context):
        started.append("first")
        return 1

    def second(_context):
        started.append("second")
        return 2

    plan = (
        ResearchWave("wave-1", (ResearchBranch("duplicate", first),)),
        ResearchWave("wave-2", (ResearchBranch("duplicate", second),)),
    )

    with pytest.raises(ValueError, match="unique across the research plan"):
        ParallelResearchExecutor(max_workers=2).run(plan)

    assert started == []


def test_duplicate_wave_ids_are_rejected_before_execution() -> None:
    started: list[str] = []

    def branch(_context):
        started.append("started")
        return 1

    plan = (
        ResearchWave("duplicate-wave", (ResearchBranch("a", branch),)),
        ResearchWave("duplicate-wave", (ResearchBranch("b", branch),)),
    )

    with pytest.raises(ValueError, match="wave_id values must be unique"):
        ParallelResearchExecutor(max_workers=2).run(plan)

    assert started == []


def test_executor_factory_is_used_and_shutdown_between_waves() -> None:
    class RecordingExecutor(Executor):
        def __init__(self) -> None:
            self.submissions: list[tuple[object, object]] = []
            self.shutdown_calls = 0

        def submit(
            self,
            fn: Callable[..., _T],
            /,
            *args: Any,
            **kwargs: Any,
        ) -> Future[_T]:
            future: Future[_T] = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)
            self.submissions.append((fn, args))
            return future

        def shutdown(self, *, wait=True, cancel_futures=False) -> None:
            assert wait is True
            assert cancel_futures is True
            self.shutdown_calls += 1

    executors: list[RecordingExecutor] = []

    def factory(_max_workers):
        executor = RecordingExecutor()
        executors.append(executor)
        return executor

    result = ParallelResearchExecutor(
        max_workers=2,
        executor_factory=factory,
    ).run(
        (
            ResearchWave("wave-1", (ResearchBranch("a", lambda _ctx: "a"),)),
            ResearchWave("wave-2", (ResearchBranch("b", lambda _ctx: "b"),)),
        )
    )

    assert result.by_branch_id() == {"a": "a", "b": "b"}
    assert len(executors) == 2
    assert all(executor.shutdown_calls == 1 for executor in executors)
    assert [len(executor.submissions) for executor in executors] == [1, 1]


def test_result_preserves_dependency_wave_identity() -> None:
    result = ParallelResearchExecutor(max_workers=1).run(
        (
            ResearchWave("snapshot-derived", (ResearchBranch("a", lambda _ctx: 1),)),
            ResearchWave("evidence-derived", (ResearchBranch("b", lambda _ctx: 2),)),
        )
    )

    assert result.wave_ids == ("snapshot-derived", "evidence-derived")
    assert len(result.wave_ids) == len(result.waves)
