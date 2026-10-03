#!/usr/bin/env python3
"""Fail CI when any /v1 FastAPI route lacks a canonical authorization decorator."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "researchos" / "saas"
HTTP_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def decorator_call(node: ast.AST, name: str) -> ast.Call | None:
    if not isinstance(node, ast.Call):
        return None
    target = node.func
    if isinstance(target, ast.Name) and target.id == name:
        return node
    if isinstance(target, ast.Attribute) and target.attr == name:
        return node
    return None


def route_path(decorator: ast.AST) -> str | None:
    call = next(
        (decorator_call(decorator, method) for method in HTTP_DECORATORS),
        None,
    )
    if call is None or not call.args:
        return None
    return literal_string(call.args[0])


def permission_args(decorator: ast.AST) -> tuple[str, str] | None:
    call = decorator_call(decorator, "require_permission")
    if call is None or len(call.args) < 2:
        return None
    resource = literal_string(call.args[0])
    action = literal_string(call.args[1])
    if resource is None or action is None:
        return None
    return resource, action


def main() -> int:
    routes: list[dict[str, object]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            path_value = next(
                (value for decorator in node.decorator_list if (value := route_path(decorator))),
                None,
            )
            if not path_value or not path_value.startswith("/v1/"):
                continue
            permissions = [
                value for decorator in node.decorator_list
                if (value := permission_args(decorator)) is not None
            ]
            routes.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "line": node.lineno,
                    "function": node.name,
                    "path": path_value,
                    "permission": permissions[0] if permissions else None,
                    "permission_count": len(permissions),
                }
            )

    missing = [route for route in routes if route["permission"] is None]
    malformed = [route for route in routes if route["permission_count"] != 1]
    print(f"routes={len(routes)} covered={len(routes) - len(missing)}")
    for route in routes:
        print(
            f'{route["file"]}:{route["line"]} '
            f'{route["path"]} -> {route["permission"]}'
        )

    if missing:
        print("MISSING_AUTHZ_DECORATOR")
        for route in missing:
            print(route)
    if malformed:
        print("INVALID_AUTHZ_DECORATOR_COUNT")
        for route in malformed:
            print(route)
    return 1 if missing or malformed else 0


if __name__ == "__main__":
    raise SystemExit(main())
