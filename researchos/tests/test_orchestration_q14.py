"""
Q14 — Orchestration Layer Tests.

Verifies the orchestration layer is a PURE COORDINATOR:

    DatasetBuilder -> WalkForwardValidator -> Trainer -> PipelineReport

Constraints under test:
    * No persistence, no repository/registry writes, no graph mutation.
    * Returns an immutable ``PipelineReport``.
    * Report carries the produced registry-style ``ModelContract`` and
      pure evidence descriptors (nodes/edges) for downstream layers.
    * Dependency injection only; deterministic; stdlib only.
    * No modifications to locked modules (source-level guard scan).
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import unittest

from researchos.orchestration import (
    ORCHESTRATION_VERSION,
    EvidenceEdgeDescriptor,
    EvidenceNodeDescriptor,
    OrchestrationError,
    PipelineReport,
    PipelineStage,
    PipelineStatus,
    ResearchOrchestrator,
)
from researchos.orchestration.engine import (
    _dataset_hash,
    _make_edge_id,
    _make_node_id,
    _make_pipeline_id,
)
from researchos.quant_engine.machine_learning.dataset_contracts import (
    ResearchDataset,
)
from researchos.quant_engine.models.contracts import (
    ModelContract as RegistryModelContract,
)
from researchos.quant_engine.training.training_result import TrainingResult
from researchos.quant_engine.validation.contracts import ValidationResult

_ORCH_DIR = os.path.join(os.path.dirname(__file__), "..", "orchestration")


def _make_ohlcv(n: int = 300, start: float = 100.0, step: float = 0.5):
    """Deterministic synthetic OHLCV series."""
    close = [start + i * step for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    volume = [1000.0 + i * 10.0 for i in range(n)]
    return close, high, low, volume


def _pipeline_kwargs(n: int = 300):
    close, high, low, volume = _make_ohlcv(n)
    return dict(
        close=close,
        high=high,
        low=low,
        volume=volume,
        label_horizon=1,
        label_type="binary",
        train_size=80,
        validation_size=20,
        step_size=20,
        model_id="q14_test_model_v1",
        model_name="Q14 Test Model",
        model_type="feature_weight",
        model_version="1.0.0",
        created_at="2024-01-01T00:00:00Z",
        metadata={"source": "unit-test"},
    )


class TestPublicAPI(unittest.TestCase):
    """The orchestration package exposes the expected public API."""

    def test_version(self):
        self.assertEqual(ORCHESTRATION_VERSION, "1.0.0")

    def test_enum_stages(self):
        self.assertEqual(
            [s.value for s in PipelineStage],
            ["dataset", "validation", "training", "complete"],
        )

    def test_enum_statuses(self):
        self.assertEqual(
            [s.value for s in PipelineStatus],
            ["pending", "running", "completed", "failed"],
        )

    def test_contracts_are_frozen(self):
        for cls in (
            PipelineReport,
            EvidenceNodeDescriptor,
            EvidenceEdgeDescriptor,
        ):
            self.assertTrue(dataclasses.is_dataclass(cls))
            self.assertTrue(cls.__dataclass_params__.frozen, cls.__name__)

    def test_orchestrator_exposes_expected_methods(self):
        methods = {m for m in dir(ResearchOrchestrator) if not m.startswith("_")}
        self.assertIn("build_dataset", methods)
        self.assertIn("validate", methods)
        self.assertIn("train", methods)
        self.assertIn("run_pipeline", methods)


class TestDeterministicHelpers(unittest.TestCase):
    """The internal hash helpers are deterministic and stable."""

    def test_pipeline_id_deterministic(self):
        kw = _pipeline_kwargs()
        id1 = _make_pipeline_id(
            kw["close"],
            kw["high"],
            kw["low"],
            kw["volume"],
            kw["model_id"],
            kw["train_size"],
            kw["validation_size"],
            kw["step_size"],
        )
        id2 = _make_pipeline_id(
            kw["close"],
            kw["high"],
            kw["low"],
            kw["volume"],
            kw["model_id"],
            kw["train_size"],
            kw["validation_size"],
            kw["step_size"],
        )
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in id1))

    def test_node_and_edge_ids_deterministic(self):
        self.assertEqual(
            _make_node_id("dataset", "abc", "model_1"),
            _make_node_id("dataset", "abc", "model_1"),
        )
        self.assertEqual(
            _make_edge_id("a", "b", "trains"),
            _make_edge_id("a", "b", "trains"),
        )

    def test_dataset_hash_deterministic_and_content_sensitive(self):
        close, high, low, volume = _make_ohlcv(120)
        ds1 = ResearchOrchestrator().build_dataset(
            close,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        ds2 = ResearchOrchestrator().build_dataset(
            close,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        self.assertEqual(_dataset_hash(ds1), _dataset_hash(ds2))
        # A perturbed dataset produces a different hash.
        close3 = [c + 0.001 for c in close]
        ds3 = ResearchOrchestrator().build_dataset(
            close3,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        self.assertNotEqual(_dataset_hash(ds1), _dataset_hash(ds3))


class TestStepMethods(unittest.TestCase):
    """Individual pipeline steps delegate to the locked modules."""

    def test_build_dataset_returns_research_dataset(self):
        close, high, low, volume = _make_ohlcv(200)
        ds = ResearchOrchestrator().build_dataset(
            close,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        self.assertIsInstance(ds, ResearchDataset)
        self.assertGreater(ds.sample_count, 0)
        self.assertGreater(ds.feature_count, 0)
        self.assertEqual(ds.label_name, "binary")

    def test_validate_returns_validation_result(self):
        close, high, low, volume = _make_ohlcv(300)
        orch = ResearchOrchestrator()
        ds = orch.build_dataset(
            close,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        vr = orch.validate(
            ds,
            train_size=80,
            validation_size=20,
            step_size=20,
        )
        self.assertIsInstance(vr, ValidationResult)
        self.assertGreater(vr.fold_count, 0)

    def test_train_returns_training_result(self):
        close, high, low, volume = _make_ohlcv(300)
        orch = ResearchOrchestrator()
        ds = orch.build_dataset(
            close,
            high,
            low,
            volume,
            label_horizon=1,
            label_type="binary",
        )
        tr = orch.train(
            ds,
            model_id="q14_train_v1",
            name="Q14 Train",
            model_type="feature_weight",
            version="1.0.0",
            created_at="2024-01-01T00:00:00Z",
        )
        self.assertIsInstance(tr, TrainingResult)
        self.assertEqual(tr.n_samples, ds.sample_count)

    def test_unknown_label_type_raises(self):
        close, high, low, volume = _make_ohlcv(100)
        with self.assertRaises(OrchestrationError):
            ResearchOrchestrator().build_dataset(
                close,
                high,
                low,
                volume,
                label_horizon=1,
                label_type="bogus",
            )


class TestRunPipeline(unittest.TestCase):
    """Full-pipeline behaviour on the success path."""

    def test_success_path_report(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        self.assertIsInstance(report, PipelineReport)
        self.assertEqual(report.status, PipelineStatus.COMPLETED)
        self.assertGreater(report.sample_count, 0)
        self.assertGreater(report.feature_count, 0)
        self.assertTrue(report.dataset_hash)
        self.assertTrue(report.feature_names)
        self.assertTrue(report.label_name)

    def test_model_contract_is_registry_style(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        mc = report.model_contract
        self.assertIsInstance(mc, RegistryModelContract)
        # Registry-style fields (not training-style).
        self.assertTrue(mc.algorithm)
        self.assertTrue(mc.dataset_hash)
        self.assertTrue(mc.validation_hash)
        self.assertEqual(mc.model_id, "q14_test_model_v1")
        self.assertEqual(mc.version, "1.0.0")
        self.assertEqual(tuple(mc.feature_names), report.feature_names)

    def test_report_carries_validation_and_training(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        self.assertIsInstance(report.validation, ValidationResult)
        self.assertIsInstance(report.training, TrainingResult)

    def test_evidence_descriptors_present(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        self.assertGreater(len(report.nodes), 0)
        self.assertGreater(len(report.edges), 0)
        for node in report.nodes:
            self.assertIsInstance(node, EvidenceNodeDescriptor)
        for edge in report.edges:
            self.assertIsInstance(edge, EvidenceEdgeDescriptor)
        node_types = {n.node_type for n in report.nodes}
        self.assertIn("dataset", node_types)
        self.assertIn("model", node_types)
        self.assertIn("validation", node_types)

    def test_determinism(self):
        orch = ResearchOrchestrator()
        r1 = orch.run_pipeline(**_pipeline_kwargs())
        r2 = orch.run_pipeline(**_pipeline_kwargs())
        self.assertEqual(r1.to_dict(), r2.to_dict())
        self.assertEqual(r1.content_hash(), r2.content_hash())
        self.assertEqual(r1.pipeline_id, r2.pipeline_id)
        self.assertEqual(hash(r1), hash(r2))

    def test_immutability(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            report.sample_count = 999  # type: ignore[misc]

    def test_serialization_roundtrip(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        restored = PipelineReport.from_dict(report.to_dict())
        self.assertEqual(restored.to_dict(), report.to_dict())
        self.assertEqual(restored.content_hash(), report.content_hash())
        self.assertEqual(restored, report)

    def test_metadata_forwarded(self):
        orch = ResearchOrchestrator()
        report = orch.run_pipeline(**_pipeline_kwargs())
        self.assertEqual(dict(report.metadata), {"source": "unit-test"})


class TestRunPipelineFailure(unittest.TestCase):
    """The error path returns a minimal FAILED report, never raises."""

    def test_too_small_dataset_fails_gracefully(self):
        orch = ResearchOrchestrator()
        # n=30 is far below the feature warmup; the aligned dataset is empty
        # and walk-forward validation rejects it.
        kw = _pipeline_kwargs(n=30)
        report = orch.run_pipeline(**kw)
        self.assertIsInstance(report, PipelineReport)
        self.assertEqual(report.status, PipelineStatus.FAILED)
        self.assertEqual(report.sample_count, 0)
        self.assertIn("error", dict(report.metadata))
        # The failed report still carries a registry-style contract.
        self.assertIsInstance(report.model_contract, RegistryModelContract)

    def test_invalid_model_type_fails_gracefully(self):
        orch = ResearchOrchestrator()
        kw = _pipeline_kwargs()
        kw["model_type"] = "not_a_real_model"
        report = orch.run_pipeline(**kw)
        self.assertIsInstance(report, PipelineReport)
        self.assertEqual(report.status, PipelineStatus.FAILED)


class TestPurityGuards(unittest.TestCase):
    """Source-level guards: the orchestrator must remain a pure coordinator."""

    def _orchestration_source(self) -> str:
        parts = []
        for name in ("contracts.py", "engine.py", "__init__.py"):
            path = os.path.join(_ORCH_DIR, name)
            with open(path, encoding="utf-8") as fh:
                parts.append(fh.read())
        return "\n".join(parts)

    def test_no_registry_mutation(self):
        src = self._orchestration_source()
        self.assertNotIn("ModelRegistry", src)
        self.assertNotIn("register(", src)

    def test_no_graph_construction(self):
        src = self._orchestration_source()
        self.assertNotIn("EvidenceGraph", src)
        self.assertNotIn("add_node(", src)
        self.assertNotIn("add_edge(", src)

    def test_no_repository_persistence(self):
        src = self._orchestration_source()
        for forbidden in ("repository.", "Repository", ".save(", "persist("):
            self.assertNotIn(forbidden, src)

    def test_stdlib_only_imports(self):
        with open(os.path.join(_ORCH_DIR, "engine.py"), encoding="utf-8") as f:
            engine_src = f.read()
        compile(engine_src, "engine.py", "exec")
        # Compilation succeeds (already proven), and the import section only
        # references the project package plus the stdlib.
        self.assertIn("import hashlib", engine_src)
        self.assertIn("import json", engine_src)
        self.assertNotIn("import numpy", engine_src)
        self.assertNotIn("import pandas", engine_src)
        self.assertNotIn("import sklearn", engine_src)

    def test_no_singleton_or_global_mutable_state(self):
        with open(os.path.join(_ORCH_DIR, "engine.py"), encoding="utf-8") as f:
            engine_src = f.read()
        # Use a multi-line docstring check: the engine __init__ docstring
        # mentions "no global state" but we want to ensure no actual
        # Python-level 'global ' keyword statement exists.
        import ast

        tree = ast.parse(engine_src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                self.fail(f"engine.py uses Python 'global' keyword: {node.names}")
        self.assertNotIn("Singleton", engine_src)
        # The docstring mentions "no randomness" so a substring check for
        # 'random' would false-positive; check for actual random imports.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "random" or alias.name.startswith("random."):
                        self.fail(f"engine.py imports random module: {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "random" or node.module.startswith("random.")):
                    self.fail(f"engine.py imports from random module: {node.module}")

    def test_dependency_injection_only(self):
        sig = inspect.signature(ResearchOrchestrator.__init__)
        params = list(sig.parameters)
        self.assertEqual(params[0], "self")
        self.assertIn("dataset_builder", params)
        self.assertIn("validator", params)
        self.assertIn("trainer", params)
        # All injected deps default to None -> orchestrator constructs them.
        self.assertIsNone(sig.parameters["dataset_builder"].default)
        self.assertIsNone(sig.parameters["validator"].default)
        self.assertIsNone(sig.parameters["trainer"].default)


if __name__ == "__main__":
    unittest.main()
