from __future__ import annotations

from scripts.confirm_xauusd_m1_frozen_candidate import _finalize_scientific_gate


def test_b_level_promotion_is_blocked_until_external_controls_are_verified() -> None:
    result = {
        "scientific_gate": "B_LEVEL_PASS",
        "gate": {
            "source_to_result_audit": True,
            "walk_forward_audit": True,
        },
        "negative_controls": {
            "label_shuffle_control": "REQUIRED_SEPARATE_RUN",
            "temporal_leakage_control": "REQUIRED_SEPARATE_RUN",
        },
    }

    finalized = _finalize_scientific_gate(result)

    assert finalized["scientific_gate"] == "NO_EDGE_OR_INCONCLUSIVE"
    assert finalized["gate"]["external_controls_verified"] is False


def test_b_level_promotion_requires_all_external_controls() -> None:
    result = {
        "scientific_gate": "B_LEVEL_PASS",
        "gate": {
            "source_to_result_audit": True,
            "walk_forward_audit": True,
        },
        "negative_controls": {
            "label_shuffle_control": "VERIFIED",
            "temporal_leakage_control": "VERIFIED",
        },
    }

    finalized = _finalize_scientific_gate(result)

    assert finalized["scientific_gate"] == "B_LEVEL_PASS"
