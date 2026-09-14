from __future__ import annotations

import json

import pytest

from researchos.research_adapters import FrozenXauusdM1Pipeline
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

    artifacts = tuple(FrozenXauusdM1Pipeline(lambda _request: b"raw-csv")(_request()))

    assert calls == ["real", "walkforward", "calibration"]
    assert [artifact.kind for artifact in artifacts] == [
        "xauusd_m1_real_events",
        "xauusd_m1_walkforward",
        "xauusd_m1_oos_calibration",
    ]
    assert all(len(artifact.content) > 0 for artifact in artifacts)
