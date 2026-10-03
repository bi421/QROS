"""Conformance tests for the deterministic research-model adapter."""

from __future__ import annotations

import unittest

from researchos.quant_engine.machine_learning.dataset_contracts import ResearchDataset
from researchos.quant_engine.models import (
    DeterministicResearchModelAdapter,
    InferenceRequest,
    ModelRuntime,
)
from researchos.quant_engine.training.contracts import ModelType
from researchos.quant_engine.training.trainer import Trainer, dataset_hash


def _dataset() -> ResearchDataset:
    return ResearchDataset(
        feature_names=("f1", "f2"),
        features=((1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (0.0, 2.0)),
        labels=(1.0, 1.0, 0.0, 0.0),
        sample_count=4,
        feature_count=2,
        label_name="target",
    )


def _model():
    result = Trainer().train_feature_weight(
        _dataset(),
        model_id="deterministic_test_v1",
        name="Deterministic Test",
    )
    return result.model


def _request(dataset: ResearchDataset | None = None) -> InferenceRequest:
    dataset = dataset or _dataset()
    return InferenceRequest(
        dataset_hash=dataset_hash(dataset),
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-01T00:10:00Z",
        input_schema=tuple(dataset.feature_names),
        payload=dataset,
    )


class TestDeterministicResearchModelAdapter(unittest.TestCase):
    def test_runtime_executes_real_trained_model(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        runtime = ModelRuntime()
        runtime.register(adapter)
        runtime.load(model.model_id)

        result = runtime.predict(model.model_id, _request())

        self.assertEqual(result.model_id, model.model_id)
        self.assertEqual(result.model_version, model.version)
        self.assertEqual(result.dataset_hash, dataset_hash(_dataset()))
        self.assertEqual(len(result.predictions), 4)
        self.assertEqual(
            result.metadata["model_type"],
            ModelType.FEATURE_WEIGHT.value,
        )

    def test_execution_is_deterministic(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        runtime = ModelRuntime()
        runtime.register(adapter)
        runtime.load(model.model_id)

        first = runtime.predict(model.model_id, _request())
        second = runtime.predict(model.model_id, _request())

        self.assertEqual(first, second)

    def test_rejects_non_dataset_payload(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        request = _request()
        bad_request = InferenceRequest(
            dataset_hash=request.dataset_hash,
            window_start=request.window_start,
            window_end=request.window_end,
            input_schema=request.input_schema,
            payload={"features": []},
        )
        adapter.load()

        with self.assertRaises(TypeError):
            adapter.predict(bad_request)

    def test_rejects_payload_hash_mismatch(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        dataset = _dataset()
        request = InferenceRequest(
            dataset_hash="sha256:not-the-payload",
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-01T00:10:00Z",
            input_schema=dataset.feature_names,
            payload=dataset,
        )
        adapter.load()

        with self.assertRaises(ValueError):
            adapter.predict(request)

    def test_rejects_schema_mismatch(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        dataset = _dataset()
        request = InferenceRequest(
            dataset_hash=dataset_hash(dataset),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-01T00:10:00Z",
            input_schema=("f2", "f1"),
            payload=dataset,
        )
        adapter.load()

        with self.assertRaises(ValueError):
            adapter.predict(request)

    def test_rejects_request_parameters_that_would_be_ignored(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        base = _request()
        request = InferenceRequest(
            dataset_hash=base.dataset_hash,
            window_start=base.window_start,
            window_end=base.window_end,
            input_schema=base.input_schema,
            payload=base.payload,
            parameters={"unexpected": 1},
        )
        adapter.load()

        with self.assertRaises(ValueError):
            adapter.predict(request)

    def test_rejects_seed_that_is_not_consumed(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        base = _request()
        request = InferenceRequest(
            dataset_hash=base.dataset_hash,
            window_start=base.window_start,
            window_end=base.window_end,
            input_schema=base.input_schema,
            payload=base.payload,
            seed=7,
        )
        adapter.load()

        with self.assertRaises(ValueError):
            adapter.predict(request)


if __name__ == "__main__":
    unittest.main()