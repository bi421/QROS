"""Namespace compatibility tests for the canonical quant capabilities API."""

from __future__ import annotations

import pytest

from researchos.engines.quant import capabilities as legacy
from researchos.quant_engine import capabilities as canonical
from researchos.quant_engine.backend import PythonQuantBackend


def test_legacy_exports_are_canonical_identities() -> None:
    assert legacy.QUANT_OPERATIONS is canonical.QUANT_OPERATIONS
    assert legacy.REFERENCE_BACKEND_NAME == canonical.REFERENCE_BACKEND_NAME
    assert legacy.REFERENCE_BACKEND_VERSION == canonical.REFERENCE_BACKEND_VERSION
    assert legacy.BackendCapabilities is canonical.BackendCapabilities
    assert legacy.BackendCapabilitiesError is canonical.BackendCapabilitiesError
    assert legacy.default_capabilities is canonical.default_capabilities


def test_legacy_capabilities_preserve_validation_and_serialization() -> None:
    caps = legacy.BackendCapabilities(
        backend_name="TestBackend",
        version="1.2.3",
        supported_operations=["calculate_returns", "run_simulation"],
        deterministic=False,
    )

    assert caps.supports("calculate_returns")
    assert not caps.supports("calculate_metrics")
    assert caps.to_dict() == {
        "backend_name": "TestBackend",
        "version": "1.2.3",
        "supported_operations": ["calculate_returns", "run_simulation"],
        "deterministic": False,
        "stateless": True,
        "no_timestamps": True,
        "no_randomness": True,
        "explicit_typing": True,
    }
    assert legacy.BackendCapabilities.from_dict(caps.to_dict()) == caps


@pytest.mark.parametrize(
    "kwargs",
    [
        {"backend_name": "", "version": "1.0.0", "supported_operations": ()},
        {"backend_name": "Backend", "version": "", "supported_operations": ()},
        {"backend_name": "Backend", "version": "1.0.0", "supported_operations": "bad"},
    ],
)
def test_legacy_capabilities_preserve_validation_errors(kwargs: dict[str, object]) -> None:
    with pytest.raises(legacy.BackendCapabilitiesError):
        legacy.BackendCapabilities(**kwargs)


def test_legacy_default_capabilities_preserve_backend_contract() -> None:
    caps = legacy.default_capabilities(PythonQuantBackend())

    assert caps.backend_name == "PythonQuantBackend"
    assert caps.version == "1.0.0"
    assert caps.supported_operations == canonical.QUANT_OPERATIONS
    assert caps.deterministic is True
    assert caps.stateless is True
    assert caps.no_timestamps is True
    assert caps.no_randomness is True
    assert caps.explicit_typing is True
