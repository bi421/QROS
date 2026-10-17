"""Write SHA-256 manifest for the 2026-10-17 follow-up research artifacts."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / ".gitignore",
    ROOT / "config/costs.yaml",
    ROOT / "config/forward_validation_preregistration_20261017.json",
    ROOT / "docs/QROS_COST_EVIDENCE_V1.md",
    ROOT / "docs/MT5_DEMO_FILL_LOG_TEMPLATE.md",
    ROOT / "researchos/orchestration/xauusd_cost_model.py",
    ROOT / "scripts/analyze_follow_missing_data_bias.py",
    ROOT / "scripts/reassess_order_type_slippage.py",
    ROOT / "scripts/import_mt5_fill_slippage.py",
    ROOT / "scripts/create_forward_preregistration.py",
    ROOT / "scripts/check_cross_instrument_readiness.py",
    ROOT / "scripts/reassess_follow_pairs_with_trade_costs.py",
    ROOT / "scripts/run_qros_bnf_cost_screen.py",
    ROOT / "tests/unit/test_xauusd_cost_model.py",
    ROOT / "tests/unit/test_import_mt5_fill_slippage.py",
    ROOT / "artifacts/qros_follow_missing_data_bias_20261017.json",
    ROOT / "artifacts/qros_follow_order_type_slippage_20261017.json",
    ROOT / "artifacts/qros_follow_order_type_slippage_20261017.sha256",
    ROOT / "artifacts/qros_follow_19_cost_reassessment_20261017.json",
    ROOT / "artifacts/qros_historical_trial_registry_20261017.json",
    ROOT / "artifacts/qros_bnf_cost_first_screen_20261017.json",
    ROOT / "artifacts/qros_cross_instrument_readiness_20261017.json",
    ROOT / "artifacts/qros_follow_19_costed_trade_rows_20261017.parquet",
    ROOT / "artifacts/qros_follow_19_order_type_costed_trades_20261017.parquet",
]
OUTPUT = ROOT / "artifacts/qros_follow_up_evidence_20261017.sha256"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> None:
    missing = [str(path.relative_to(ROOT)) for path in FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"EVIDENCE_FILES_MISSING:{missing}")
    OUTPUT.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in FILES),
        encoding="ascii",
    )
    print(f"manifest={OUTPUT.relative_to(ROOT)}")
    print(f"entries={len(FILES)}")
    print(f"sha256={sha256(OUTPUT)}")


if __name__ == "__main__":
    run()
