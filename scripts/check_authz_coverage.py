#!/usr/bin/env python3
"""Fail CI when a protected SaaS route is missing explicit authorization."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAAS_DIR = ROOT / "researchos" / "saas"

# Route objects used across the SaaS boundary: FastAPI(app) and APIRouter(router).
ROUTE_OBJECTS = frozenset({"app", "router"})
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

PUBLIC_PREFIXES = ("/healthz", "/readyz", "/metrics", "/v1/me", "/v1/billing/webhook")
PUBLIC_ROUTES = {"/onboarding", "/onboarding/app.js", "/onboarding/config"}
IDENTITY_ONLY_ROUTES = {"/v1/workspaces"}


def _route_paths(node: ast.AST) -> list[str]:
    paths: list[str] = []
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in ROUTE_OBJECTS
            and target.attr in HTTP_METHODS
        ):
            continue
        if (
            isinstance(decorator, ast.Call)
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and isinstance(decorator.args[0].value, str)
        ):
            paths.append(decorator.args[0].value)
    return paths


def _has_permission(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "require_permission":
            return True
    return False


def _has_identity_auth(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "auth"
            and target.attr == "authenticate_user"
        ):
            return True
    return False


def scan_file(api_file: Path, missing: list[str]) -> int:
    tree = ast.parse(api_file.read_text(encoding="utf-8"))
    route_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths = _route_paths(node)
        if not route_paths:
            continue
        has_permission = _has_permission(node)
        has_identity_auth = _has_identity_auth(node)
        for route in route_paths:
            route_count += 1
            if route in PUBLIC_ROUTES or route.startswith(PUBLIC_PREFIXES):
                continue
            if route in IDENTITY_ONLY_ROUTES and has_identity_auth:
                continue
            if not has_permission:
                missing.append(f"{api_file.name}:{node.name}: {route}")
    return route_count


def main() -> int:
    missing: list[str] = []
    route_count = 0
    for api_file in sorted(SAAS_DIR.glob("*.py")):
        route_count += scan_file(api_file, missing)

    if missing:
        raise SystemExit("protected routes missing require_permission: " + "; ".join(sorted(missing)))
    print(f"authorization coverage OK: {route_count} registered routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
