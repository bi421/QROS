"""Tests for deterministic parallel research orchestration."""

from __future__ import annotations

import threading

import pytest

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
