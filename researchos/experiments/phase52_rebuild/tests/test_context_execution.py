from __future__ import annotations

from datetime import date, timedelta

from researchos.experiments.phase52.contracts import Phase52Result
from researchos.experiments.phase52.experiment import Phase52Config
from researchos.experiments.phase52_rebuild.context_execution import (
    run_context_aware_phase52_comparison,
)
from researchos.experiments.phase52_rebuild.context_features import (
    ContextFeatureAudit,
)
from researchos.experiments.phase52_rebuild.context_pipeline import (
    ContextAwareFeatureBuild,
)
from researchos.experiments.phase52_rebuild.daily_dataset import DailyObservation
from researchos.experiments.phase52_rebuild.feature_contract import FEATURE_SET_NAMES
from researchos.experiments.phase52_rebuild.feature_dataset import FeatureDataset


def _obs(day_index: int) -> DailyObservation:
    day = date(2020, 1, 1) + timedelta(days=day_index)
    iso = day.isoformat()
    return DailyObservation(
        day=iso,
        timestamp=f"{iso}T00:00:00Z",
        open=100.0 + day_index * 0.1,
        high=101.0 + day_index * 0.1,
        low=99.0 + day_index * 0.1,
        close=100.5 + day_index * 0.1,
        tick_volume=100.0,
        spread=1.0,
        real_volume=0.0,
        vwap=100.2 + day_index * 0.1,
        dxy=100.0 + day_index * 0.01,
        us10y=1.0 + day_index * 0.001,
        vix=20.0 + day_index * 0.01,
        m1_rows=1440,
    )


def _build(context_count: int = 60, research_count: int = 205) -> ContextAwareFeatureBuild:
    context = tuple(_obs(i) for i in range(context_count))
    research = tuple(_obs(context_count + i) for i in range(research_count))
    emitted = research_count - 5
    datasets = {
        name: FeatureDataset(
            feature_set=name,
            feature_names=("x",),
            rows=tuple((1.0,) for _ in range(emitted)),
            labels=tuple(1 for _ in range(emitted)),
            source_days=tuple(o.day for o in research[:-5]),
            prediction_timestamps=tuple(o.timestamp for o in research[:-5]),
            metadata={
                "context_is_feature_state_only": True,
                "context_rows_emitted": False,
                "no_interpolation_or_forward_fill": True,
                "source_indices": list(range(emitted)),
            },
        )
        for name in FEATURE_SET_NAMES
    }
    audits = {
        name: ContextFeatureAudit(
            context_rows=context_count,
            research_rows=research_count,
            warmup_rows=60,
            label_horizon=5,
            emitted_rows=emitted,
            expected_emitted_rows=emitted,
            context_sufficient=context_count >= 60,
        )
        for name in FEATURE_SET_NAMES
    }
    return ContextAwareFeatureBuild(context, research, datasets, audits)


def test_context_execution_uses_research_rows_only(monkeypatch) -> None:
    build = _build()
    calls: list[tuple[str, int, tuple[int, ...], int]] = []

    def fake_run(prepared, config):
        calls.append((config.feature_set, len(prepared.close), prepared.source_indices, id(prepared)))
        assert len(prepared.close) == 205
        assert prepared.source_indices == tuple(range(200))
        return Phase52Result.blocked(
            symbol=config.symbol,
            timeframe=config.timeframe,
            reason="test",
            macro_symbols_present=("DXY", "US10Y", "VIX"),
        )

    monkeypatch.setattr(
        "researchos.experiments.phase52_rebuild.context_execution._run_prepared",
        fake_run,
    )
    results = run_context_aware_phase52_comparison(
        build,
        Phase52Config(train_size=100, validation_size=100),
    )

    assert set(results) == set(FEATURE_SET_NAMES)
    assert len(calls) == len(FEATURE_SET_NAMES)
    assert all(call[1] == 205 for call in calls)
    assert all(call[2] == tuple(range(200)) for call in calls)
    assert len({call[3] for call in calls}) == 1


def test_context_execution_rejects_source_index_mismatch(monkeypatch) -> None:
    build = _build()
    broken = build.datasets["PRICE_ONLY"]
    broken.metadata["source_indices"] = [1]  # type: ignore[index]
    monkeypatch.setattr(
        "researchos.experiments.phase52_rebuild.context_execution._run_prepared",
        lambda prepared, config: None,
    )
    try:
        run_context_aware_phase52_comparison(
            build,
            Phase52Config(train_size=100, validation_size=100),
        )
    except AssertionError as exc:
        assert "source-index contract failed" in str(exc)
    else:
        raise AssertionError("expected source-index contract failure")
