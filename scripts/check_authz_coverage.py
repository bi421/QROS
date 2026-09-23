#!/usr/bin/env python3
"""Fail CI when a protected SaaS route is missing explicit authorization."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "researchos" / "saas" / "api.py"


def main() -> int:
    tree = ast.parse(API.read_text(encoding="utf-8"))
    route_count = 0
    missing: list[str] = []
    public_prefixes = ("/healthz", "/readyz", "/metrics", "/v1/me", "/v1/billing/webhook")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths: list[str] = []
        has_permission = False
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "app":
                if target.attr in {"get", "post", "put", "patch", "delete"} and isinstance(decorator, ast.Call):
                    if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
                        route_paths.append(decorator.args[0].value)
            if isinstance(target, ast.Name) and target.id == "require_permission":
                has_permission = True
        for route in route_paths:
            route_count += 1
            if route.startswith(public_prefixes):
                continue
            if not has_permission:
                missing.append(f"{node.name}: {route}")

    if missing:
        raise SystemExit("protected routes missing require_permission: " + "; ".join(sorted(missing)))
    print(f"authorization coverage OK: {route_count} registered routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
