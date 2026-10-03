"""Namespace compatibility and behavior tests for the technical engine."""

import pytest

from researchos.engines.quant.technical import engine as legacy
from researchos.quant_engine.technical import engine as canonical
from researchos.quant_engine.technical.contracts import Bars, IndicatorSpec


def _bars(length: int = 30) -> Bars:
    opens = [100.0 + i * 0.5 for i in range(length)]
    return Bars(
        open=opens,
        high=[value + 1.0 for value in opens],
        low=[value - 1.0 for value in opens],
        close=[value + 0.25 for value in opens],
        volume=[1000.0 + i * 10.0 for i in range(length)],
    )


def test_legacy_engine_namespace_is_canonical() -> None:
    assert legacy.TechnicalAnalysisEngine is canonical.TechnicalAnalysisEngine
    assert legacy.get_technical_engine is canonical.get_technical_engine
    assert legacy.register_indicator is canonical.register_indicator
    assert legacy.INDICATOR_REGISTRY is canonical.INDICATOR_REGISTRY


def test_engine_computes_representative_indicator_contract() -> None:
    bars = _bars()
    spec = IndicatorSpec(name="SMA", params={"period": 5})

    output = legacy.TechnicalAnalysisEngine().compute(bars, spec)

    assert output.name == "SMA"
    assert output.category.value == "trend"
    assert output.params == {"period": 5}
    assert len(output.values) == bars.length
    assert output.values[:4] == [None, None, None, None]
    assert output.values[4] == pytest.approx(sum(bars.close[:5]) / 5.0)


def test_engine_batch_is_deterministic_and_structured() -> None:
    bars = _bars()
    specs = [
        IndicatorSpec(name="SMA", params={"period": 5}),
        IndicatorSpec(name="MACD"),
    ]

    first = canonical.get_technical_engine().compute_batch(bars, specs)
    second = canonical.get_technical_engine().compute_batch(bars, specs)

    assert first.to_dict() == second.to_dict()
    assert first.bar_count == bars.length
    assert first.computation_version == "TECHNICAL_V1"
    assert set(first.outputs) == {"SMA", "MACD"}
    assert "signal" in first.outputs["MACD"].aux
    assert "histogram" in first.outputs["MACD"].aux


def test_engine_propagates_validation_and_unknown_indicator_errors() -> None:
    malformed = Bars(
        open=[1.0, 2.0],
        high=[2.0],
        low=[0.0, 1.0],
        close=[1.5, 2.5],
        volume=[10.0, 20.0],
    )
    with pytest.raises(ValueError, match="equal length"):
        canonical.get_technical_engine().compute(malformed, IndicatorSpec(name="SMA"))

    with pytest.raises(ValueError, match="empty bar series"):
        canonical.get_technical_engine().compute(Bars(), IndicatorSpec(name="SMA"))

    with pytest.raises(KeyError, match="Unknown indicator 'NOT_REAL'"):
        canonical.get_technical_engine().compute(_bars(), IndicatorSpec(name="NOT_REAL"))


def test_engine_factory_returns_fresh_instances_with_same_contract() -> None:
    first = legacy.get_technical_engine()
    second = legacy.get_technical_engine()

    assert first is not second
    assert type(first) is canonical.TechnicalAnalysisEngine
    assert first.available_indicators == second.available_indicators
    assert first.available_indicators == sorted(canonical.INDICATOR_REGISTRY)
