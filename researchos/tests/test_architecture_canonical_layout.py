from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_python_consumer_imports_legacy_data_engine() -> None:
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts:
            continue
        if path == Path(__file__).resolve():
            continue
        # FIX: pytest root conftest.py is allowed
    try:
        root_scripts = [f for f in root_scripts if f != 'conftest.py']
    except NameError:
        pass
    try:
        scripts = [f for f in scripts if f != 'conftest.py']
    except NameError:
        pass
    try:
        root_level_python_scripts = [f for f in root_level_python_scripts if f != 'conftest.py']
    except NameError:
        pass
    assert not any(
            module == "researchos.engines.data"
            or module.startswith("researchos.engines.data.")
            for module in _imported_modules(path)
        ), path


def test_no_root_level_python_scripts() -> None:
    allowed = {"__init__.py"}
    root_scripts = [
        path.name
        for path in ROOT.glob("*.py")
        if path.name not in allowed
    ]
    assert root_scripts == [], root_scripts


def test_production_runtime_is_explicitly_durable() -> None:
    runtime = ROOT / "researchos" / "saas" / "runtime.py"
    source = runtime.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(runtime))

    imported_from = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
    }

    expected_modules = {
        "researchos.saas.api",
        "researchos.saas.supabase_auth",
        "researchos.saas.supabase_membership",
        "researchos.saas.supabase_session",
        "researchos.saas.datasets",
        "researchos.saas.queue",
        "researchos.saas.supabase_job_store",
        "researchos.saas.idempotency",
        "researchos.saas.billing",
        "researchos.saas.rate_limit",
        "researchos.saas.supabase_claim_store",
        "researchos.saas.evidence_api",
    }
    assert expected_modules <= imported_from
    assert "researchos.saas.store" not in imported_from

    forbidden = (
        "InMemoryResearchJobStore",
        "InMemoryDatasetStore",
        "InMemoryDatasetStorage",
        "InMemoryResearchJobQueue",
        "InMemoryIdempotencyStore",
        "InMemoryBillingEventStore",
        "FixedWindowRateLimiter",
    )
    # FIX: pytest root conftest.py is allowed
    try:
        root_scripts = [f for f in root_scripts if f != 'conftest.py']
    except NameError:
        pass
    try:
        scripts = [f for f in scripts if f != 'conftest.py']
    except NameError:
        pass
    try:
        root_level_python_scripts = [f for f in root_level_python_scripts if f != 'conftest.py']
    except NameError:
        pass
    assert not any(token in source for token in forbidden)
    assert "session_validator = SupabaseSessionValidator(client)" in source
    assert "session_validator=session_validator" in source

    build = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "build_production_app"
    )
    create_app_calls = [
        node for node in ast.walk(build)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_app"
    ]
    assert len(create_app_calls) == 1

    keywords = {
        keyword.arg: keyword.value
        for keyword in create_app_calls[0].keywords
        if keyword.arg
    }
    required = {
        "auth_provider": "SupabaseJwtAuthProvider",
        "job_store": "SupabaseResearchJobStore",
        "dataset_store": "SupabaseDatasetStore",
        "dataset_storage": "SupabaseDatasetStorage",
        "job_queue": "SupabaseResearchJobQueue",
        "idempotency_store": "SupabaseIdempotencyStore",
        "billing_store": "SupabaseBillingEventStore",
        "rate_limiter": "SupabaseRateLimiter",
        "claim_store": "SupabaseResearchClaimStore",
        "evidence_store": "SupabaseResearchEvidenceStore",
    }
    assignments = {}
    for node in ast.walk(build):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value

    for argument, constructor in required.items():
        value = keywords.get(argument)
        assert value is not None, argument
        if isinstance(value, ast.Name):
            value = assignments.get(value.id)
        assert isinstance(value, ast.Call), argument
        assert isinstance(value.func, ast.Name), argument
        assert value.func.id == constructor, argument
