"""Contract tests for the provider-neutral model execution boundary."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Sequence

from researchos.quant_engine.models import (
    BatchResultCountMismatchError,
    InferenceRequest,
    InferenceResult,
    ModelAdapterAlreadyExistsError,
    ModelAdapterNotFoundError,
    ModelNotReadyError,
    ModelResultMismatchError,
    ModelRuntime,
)


@dataclass
class DummyAdapter:
    model_id: str
    model_version: str = "1.0.0"
    ready: bool = False
    predict_calls: int = 0
    batch_calls: int = 0
    fail: bool = False
    mismatch_dataset: bool = False

    def load(self) -> None:
        self.ready = True

    def unload(self) -> None:
        self.ready = False

    def is_ready(self) -> bool:
        return self.ready

    def predict(self, request: InferenceRequest) -> InferenceResult:
        self.predict_calls += 1
        if self.fail:
            raise RuntimeError("adapter failure")
        dataset_hash = "wrong" if self.mismatch_dataset else request.dataset_hash
        return InferenceResult(
            model_id=self.model_id,
            model_version=self.model_version,
            dataset_hash=dataset_hash,
            predictions={"rows": 1},
        )

    def predict_batch(
        self, requests: Sequence[InferenceRequest]
    ) -> Sequence[InferenceResult]:
        self.batch_calls += 1
        return tuple(self.predict(request) for request in requests)


def _request(dataset_hash: str = "sha256:abc") -> InferenceRequest:
    return InferenceRequest(
        dataset_hash=dataset_hash,
        window_start="2026-01-01T00:00:00Z",
        window_end="2026-01-01T00:10:00Z",
        input_schema=("open", "high", "low", "close"),
        payload=((1.0, 2.0, 0.5, 1.5),),
        parameters={"lookback": 128},
        seed=42,
    )


class TestInferenceContracts(unittest.TestCase):
    def test_request_parameters_are_immutable(self) -> None:
        request = _request()
        with self.assertRaises(TypeError):
            request.parameters["lookback"] = 999  # type: ignore[index]

    def test_result_metadata_is_immutable(self) -> None:
        result = InferenceResult(
            model_id="a",
            model_version="1.0.0",
            dataset_hash="sha256:abc",
            predictions=(),
            metadata={"source": "test"},
        )
        with self.assertRaises(TypeError):
            result.metadata["source"] = "mutated"  # type: ignore[index]


class TestModelRuntime(unittest.TestCase):
    def test_register_and_list_are_deterministic(self) -> None:
        runtime = ModelRuntime()
        runtime.register(DummyAdapter("z"))
        runtime.register(DummyAdapter("a"))
        self.assertEqual(runtime.list_models(), ("a", "z"))

    def test_duplicate_registration_fails(self) -> None:
        runtime = ModelRuntime()
        runtime.register(DummyAdapter("a"))
        with self.assertRaises(ModelAdapterAlreadyExistsError):
            runtime.register(DummyAdapter("a"))

    def test_unknown_model_fails(self) -> None:
        with self.assertRaises(ModelAdapterNotFoundError):
            ModelRuntime().get("missing")

    def test_predict_requires_explicit_readiness(self) -> None:
        runtime = ModelRuntime()
        runtime.register(DummyAdapter("a"))
        with self.assertRaises(ModelNotReadyError):
            runtime.predict("a", _request())

    def test_load_predict_unload_lifecycle(self) -> None:
        runtime = ModelRuntime()
        adapter = DummyAdapter("a")
        runtime.register(adapter)

        runtime.load("a")
        self.assertTrue(runtime.is_ready("a"))

        result = runtime.predict("a", _request())
        self.assertEqual(result.model_id, "a")
        self.assertEqual(adapter.predict_calls, 1)

        runtime.unload("a")
        self.assertFalse(runtime.is_ready("a"))

    def test_no_implicit_fallback_to_another_model(self) -> None:
        runtime = ModelRuntime()
        first = DummyAdapter("a")
        second = DummyAdapter("b")
        runtime.register(first)
        runtime.register(second)
        runtime.load("a")
        first.fail = True

        with self.assertRaises(RuntimeError):
            runtime.predict("a", _request())

        self.assertEqual(first.predict_calls, 1)
        self.assertEqual(second.predict_calls, 0)

    def test_dataset_identity_mismatch_is_rejected(self) -> None:
        runtime = ModelRuntime()
        adapter = DummyAdapter("a", mismatch_dataset=True)
        runtime.register(adapter)
        runtime.load("a")

        with self.assertRaises(ModelResultMismatchError):
            runtime.predict("a", _request())

    def test_batch_preserves_cardinality(self) -> None:
        runtime = ModelRuntime()
        adapter = DummyAdapter("a")
        runtime.register(adapter)
        runtime.load("a")

        results = runtime.predict_batch("a", (_request(), _request("sha256:def")))
        self.assertEqual(len(results), 2)
        self.assertEqual(adapter.batch_calls, 1)

    def test_batch_count_mismatch_is_rejected(self) -> None:
        class ShortBatchAdapter(DummyAdapter):
            def predict_batch(
                self, requests: Sequence[InferenceRequest]
            ) -> Sequence[InferenceResult]:
                if requests:
                    return (self.predict(requests[0]),)
                return ()

        runtime = ModelRuntime()
        adapter = ShortBatchAdapter("a")
        runtime.register(adapter)
        runtime.load("a")

        with self.assertRaises(BatchResultCountMismatchError):
            runtime.predict_batch("a", (_request(), _request("sha256:def")))

    def test_runtimes_are_independent(self) -> None:
        left = ModelRuntime()
        right = ModelRuntime()
        adapter = DummyAdapter("a")
        left.register(adapter)

        self.assertEqual(left.list_models(), ("a",))
        self.assertEqual(right.list_models(), ())


if __name__ == "__main__":
    unittest.main()
