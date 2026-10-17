from __future__ import annotations

import json

import polars as pl
import pytest

from researchos.research_adapters import FrozenXauusdM1Pipeline
from researchos.research_adapters.xauusd_m1 import _build_costed_event_trades
from researchos.research_core.contracts import ResearchDataset, ResearchRequest


def _request(raw: bytes = b"raw-csv") -> ResearchRequest:
    dataset = ResearchDataset.from_content(
        dataset_id="fixture-xauusd-m1",
        asset="XAUUSD",
        timeframe="M1",
        content=raw,
        rows=({"timestamp": "2026-01-01T00:00:00Z", "close": 1.0},),
    )
    return ResearchRequest(dataset=dataset)


def test_pipeline_rejects_resolver_provenance_mismatch() -> None:
    pipeline = FrozenXauusdM1Pipeline(lambda _request: b"different")

    with pytest.raises(ValueError, match="SHA-256"):
        tuple(pipeline(_request()))


def test_pipeline_binds_all_frozen_stages(monkeypatch) -> None:
    calls: list[str] = []

    def fake_real(source, output, threshold):
        calls.append("real")
        output.write_text(json.dumps({"stage": "real"}), encoding="utf-8")
        return {"stage": "real"}

    def fake_walkforward(source, output, train_size, validation_size, step_size):
        calls.append("walkforward")
        output.write_text(json.dumps({"stage": "walkforward"}), encoding="utf-8")
        return {"stage": "walkforward"}

    def fake_calibration(source, result, output):
        calls.append("calibration")
        output.write_text(json.dumps({"stage": "calibration"}), encoding="utf-8")
        return {"stage": "calibration"}

    monkeypatch.setattr("researchos.research_adapters.xauusd_m1.run_real_pipeline", fake_real)
    monkeypatch.setattr("researchos.research_adapters.xauusd_m1.run_walkforward", fake_walkforward)
    monkeypatch.setattr("researchos.research_adapters.xauusd_m1.run_calibration", fake_calibration)
    monkeypatch.setattr("researchos.research_adapters.xauusd_m1.evaluate_xauusd_m1_run", lambda *_: {"overall_status": "INSUFFICIENT_EVIDENCE"})
    monkeypatch.setattr("researchos.research_adapters.xauusd_m1._build_costed_event_trades", lambda *_: pl.DataFrame())

    pipeline = FrozenXauusdM1Pipeline(lambda _request: b"raw-csv")
    artifacts = tuple(pipeline(_request()))
    repeated_artifacts = tuple(pipeline(_request()))

    assert calls == ["real", "walkforward", "calibration"] * 2
    assert [artifact.content for artifact in artifacts] == [artifact.content for artifact in repeated_artifacts]
    assert [artifact.kind for artifact in artifacts] == [
        "xauusd_m1_real_events",
        "xauusd_m1_costed_trades",
        "xauusd_m1_walkforward",
        "xauusd_m1_oos_calibration",
        "xauusd_m1_meta_evaluation",
    ]
    assert all(len(artifact.content) > 0 for artifact in artifacts)
    report = json.loads(artifacts[-1].content)
    assert report["research_gate"]["status"] == "NO_TRADE_COST_PROVENANCE_INVALID"
    assert report["research_gate"]["execution_authorized"] is False
    assert len(report["research_audit"]["input_sha256"]) == 64
    assert len(report["research_audit"]["decision_sha256"]) == 64
    assert report["research_audit"]["status"] == "INVALID"
    assert report["research_audit"]["failure_reason"] == "QROS_SOURCE_COMMIT_UNDECLARED_OR_INVALID"
    assert report["research_audit"]["decision"] == report["research_gate"]


def test_frozen_pipeline_trade_cost_builder_uses_bar_level_spreads() -> None:
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["time,open,high,low,close,tick_volume,spread,real_volume"]
    timestamps = []
    for i in range(40):
        ts = start + timedelta(minutes=i)
        timestamps.append(ts)
        close = 2000.0 + i * 0.1
        lines.append(f"{ts.isoformat()},{close-0.02},{close+0.2},{close-0.2},{close},100,{9 if i % 2 else 19},0")
    raw = ("\n".join(lines) + "\n").encode()
    event_index, exit_index = 20, 25
    event = {
        "event_id": "frozen-event-1",
        "timestamp": timestamps[event_index].isoformat(),
        "direction": "bullish",
        "event_price": 2000.0 + event_index * 0.1,
        "outcome": {
            "data_availability": {"realized_end_1d": timestamps[exit_index].isoformat()}
        },
    }
    trades = _build_costed_event_trades(raw, [event], "a" * 64)
    assert trades.height == 1
    row = trades.row(0, named=True)
    assert row["entry_ts"] == timestamps[event_index + 1]
    assert row["exit_ts"] == timestamps[exit_index]
    assert row["entry_spread"] == (9 if (event_index + 1) % 2 else 19)
    assert row["cost_basis_declared_x1"] is True
    assert row["costs_verified_x1"] is False
    assert row["net_return_x1"] < row["gross_return_x1"]
