from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "final_health_check.py"


def _load_health_check():
    spec = importlib.util.spec_from_file_location("qros_final_health_check", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load final_health_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_final_health_check_cli_contract_is_self_consistent() -> None:
    module = _load_health_check()
    args = module.build_parser().parse_args(
        ["--skip-cpp", "--exact-commit", "a" * 40]
    )

    assert args.skip_cpp is True
    assert args.exact_commit == "a" * 40
    assert not hasattr(args, "expected_commit")
    assert not hasattr(args, "skip_rls")


def test_final_health_check_uses_resolved_head_for_evidence() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "args.expected_commit" not in source
    assert "args.skip_rls" not in source
    assert "actual_commit" not in source
    assert '"commit": actual,' in source
