"""Contract tests for the SaaS authorization-coverage governance guard.

The guard must fail closed: every protected route registered across the SaaS
boundary -- on both ``app`` (FastAPI) and ``router`` (APIRouter) objects, in every
module -- must carry an explicit ``@require_permission`` decorator. These tests pin
that behaviour so the control cannot silently regress into a blind spot (it once
parsed only ``api.py`` and only ``app.*`` decorators). The guard itself is a hard
CI gate (``python scripts/check_authz_coverage.py``); this suite lives under
``researchos/saas/tests`` so CI executes it alongside the gate it protects.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GUARD_PATH = ROOT / "scripts" / "check_authz_coverage.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("qros_check_authz_coverage", GUARD_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_source(guard, source: str, tmp_path: Path) -> list[str]:
    module_file = tmp_path / "probe_api.py"
    module_file.write_text(source, encoding="utf-8")
    missing: list[str] = []
    guard.scan_file(module_file, missing)
    return missing


def test_guard_passes_on_real_saas_surface() -> None:
    guard = _load_guard()
    assert guard.main() == 0


def test_guard_scans_every_saas_api_module() -> None:
    guard = _load_guard()
    expected = {
        "api.py",
        "claim_api.py",
        "evidence_api.py",
        "finding_api.py",
        "validation_api.py",
    }
    scanned: set[str] = set()
    for api_file in sorted(guard.SAAS_DIR.glob("*.py")):
        missing: list[str] = []
        if guard.scan_file(api_file, missing) > 0:
            scanned.add(api_file.name)
        assert missing == [], f"{api_file.name} has unprotected routes: {missing}"
    assert expected.issubset(scanned), f"guard skipped modules: {expected - scanned}"


def test_unprotected_app_route_is_flagged(tmp_path: Path) -> None:
    guard = _load_guard()
    missing = _scan_source(
        guard,
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/v1/secret')\n"
        "def read_secret():\n"
        "    return {}\n",
        tmp_path,
    )
    assert missing == ["probe_api.py:read_secret: /v1/secret"]


def test_unprotected_router_route_is_flagged(tmp_path: Path) -> None:
    guard = _load_guard()
    missing = _scan_source(
        guard,
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/v1/secret')\n"
        "def write_secret():\n"
        "    return {}\n",
        tmp_path,
    )
    assert missing == ["probe_api.py:write_secret: /v1/secret"]


def test_require_permission_satisfies_the_guard(tmp_path: Path) -> None:
    guard = _load_guard()
    missing = _scan_source(
        guard,
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/v1/secret')\n"
        "@require_permission('secret', 'read')\n"
        "def read_secret():\n"
        "    return {}\n",
        tmp_path,
    )
    assert missing == []


def test_public_and_identity_only_routes_are_exempt(tmp_path: Path) -> None:
    guard = _load_guard()
    missing = _scan_source(
        guard,
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/healthz')\n"
        "def health():\n"
        "    return {}\n"
        "@app.get('/v1/workspaces')\n"
        "def list_workspaces():\n"
        "    auth.authenticate_user('x')\n"
        "    return {}\n",
        tmp_path,
    )
    assert missing == []
