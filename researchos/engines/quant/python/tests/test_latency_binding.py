import pytest

np = pytest.importorskip("numpy")
latency = pytest.importorskip("cpp_quant_engine.qros_latency")


def test_latency_breakdown_and_feed_clock_contract():
    parts = latency.LatencyBreakdown()
    parts.network_ns = 100
    parts.serialization_ns = 20
    parts.queue_ns = 30
    parts.processing_ns = 50
    assert latency.total_latency_ns(parts) == 200
    assert latency.observed_feed_latency_ns(1_000, 1_250) == 250
    with pytest.raises(ValueError):
        latency.observed_feed_latency_ns(1_250, 1_000)


def test_deterministic_price_projection_and_penalty():
    assert latency.project_price_after_latency(2_000.0, 2.0, 250_000_000, 0.1) == pytest.approx(2_000.6)
    penalty = latency.estimate_execution_penalty(1_000_000_000, 2.0, 0.5, 10.0, 100.0, 3.0)
    assert penalty.elapsed_seconds == pytest.approx(1.0)
    assert penalty.expected_drift_price == pytest.approx(0.5)
    assert penalty.expected_diffusion_abs_price == pytest.approx(2.0 * (2.0 / (2.0 * 3.141592653589793) ** 0.5))
    assert penalty.expected_market_impact_price == pytest.approx(0.3)
    assert penalty.order_to_liquidity_ratio == pytest.approx(0.1)
