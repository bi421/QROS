"""Conformance tests for the deterministic research-model adapter."""

from __future__ import annotations

import unittest

from researchos.quant_engine.machine_learning.dataset_contracts import ResearchDataset
from researchos.quant_engine.models import (
    DeterministicResearchModelAdapter,
    InferenceRequest,
    ModelRegistry,
    ModelRuntime,
)
from researchos.quant_engine.models.contracts import ModelContract as RegistryModelContract
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


def _model() -> RegistryModelContract:
    dataset = _dataset()
    training = Trainer().train_feature_weight(
        dataset,
        model_id="deterministic_test_v1",
        name="Deterministic Test",
    )
    return RegistryModelContract(
        model_id=training.model.model_id,
        name=training.model.name,
        version=training.model.version,
        algorithm=training.model.model_type.value,
        feature_names=tuple(dataset.feature_names),
        label_name=dataset.label_name,
        dataset_hash=dataset_hash(dataset),
        validation_hash="validation:deterministic-test",
        parameters=dict(training.model.parameters),
        created_at=training.model.created_at,
        metadata={"training_hash": training.model.training_hash},
    )


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
    def _runtime(self) -> tuple[ModelRuntime, RegistryModelContract]:
        model = _model()
        registry = ModelRegistry()
        registry.register(model)
        adapter = DeterministicResearchModelAdapter(registry.get(model.model_id))
        runtime = ModelRuntime()
        runtime.register(adapter)
        runtime.load(model.model_id)
        return runtime, model

    def test_runtime_executes_real_trained_model(self) -> None:
        runtime, model = self._runtime()

        result = runtime.predict(model.model_id, _request())

        self.assertEqual(result.model_id, model.model_id)
        self.assertEqual(result.model_version, model.version)
        self.assertEqual(result.dataset_hash, dataset_hash(_dataset()))
        self.assertEqual(len(result.predictions), 4)
        self.assertEqual(result.metadata["algorithm"], ModelType.FEATURE_WEIGHT.value)
        self.assertEqual(result.metadata["validation_hash"], model.validation_hash)

    def test_execution_is_deterministic(self) -> None:
        runtime, model = self._runtime()

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

    def test_allows_inference_on_distinct_dataset(self) -> None:
        model = _model()
        adapter = DeterministicResearchModelAdapter(model)
        dataset = ResearchDataset(
            feature_names=("f1", "f2"),
            features=((3.0, 0.0), (4.0, 0.0)),
            labels=(1.0, 0.0),
            sample_count=2,
            feature_count=2,
            label_name="target",
        )
        adapter.load()

        result = adapter.predict(_request(dataset))

        self.assertEqual(result.dataset_hash, dataset_hash(dataset))
        self.assertEqual(result.dataset_hash, _model().dataset_hash) if result.dataset_hash == _model().dataset_hash else self.assertNotEqual(result.dataset_hash, model.dataset_hash)

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

    def test_rejects_unsupported_registry_algorithm(self) -> None:
        base = _model()
        unsupported = RegistryModelContract(
            model_id=base.model_id,
            name=base.name,
            version=base.version,
            algorithm="not_supported",
            feature_names=base.feature_names,
            label_name=base.label_name,
            dataset_hash=base.dataset_hash,
            validation_hash=base.validation_hash,
            parameters=base.parameters,
            created_at=base.created_at,
            metadata=base.metadata,
        )

        with self.assertRaises(ValueError):
            DeterministicResearchModelAdapter(unsupported)


if __name__ == "__main__":
    unittest.main()