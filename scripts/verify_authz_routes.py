#!/usr/bin/env python3
"""Fail CI when any /v1 FastAPI route lacks @require_permission."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "researchos" / "saas"


def route_path(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in {"get", "post", "put", "patch", "delete"}:
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    value = decorator.args[0].value
    return value if isinstance(value, str) and value.startswith("/v1") else None


def has_permission(decorators: list[ast.expr]) -> bool:
    for decorator in decorators:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(node, ast.Name) and node.id == "require_permission":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "require_permission":
            return True
    return False


def main() -> int:
    failures: list[str] = []
    routes = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            paths = [route_path(decorator) for decorator in node.decorator_list]
            paths = [value for value in paths if value is not None]
            for route in paths:
                routes += 1
                if not has_permission(node.decorator_list):
                    relative = path.relative_to(ROOT)
                    failures.append(f"{relative}:{node.lineno} {node.name} {route}")
    if failures:
        print("Authorization route gate FAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Authorization route gate PASS: {routes} /v1 routes carry @require_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
