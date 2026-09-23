#!/usr/bin/env python3
"""Verify the executable FastAPI /v1 source surface matches API_CONTRACT_V1.md."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "saas" / "API_CONTRACT_V1.md"

EXPECTED = {
    "GET /v1/me",
    "POST /v1/billing/webhook",
    "POST /v1/datasets",
    "GET /v1/datasets",
    "POST /v1/datasets/{dataset_id}/versions",
    "GET /v1/datasets/{dataset_id}/versions",
    "GET /v1/datasets/{dataset_id}/versions/{version_id}/download",
    "POST /v1/research-runs",
    "GET /v1/research-runs",
    "GET /v1/research-runs/{job_id}",
    "GET /v1/research-runs/{job_id}/logs",
    "GET /v1/jobs/{job_id}/logs",
    "GET /v1/research-runs/{job_id}/result",
    "GET /v1/research-runs/{job_id}/evidence",
    "POST /v1/research-runs/{job_id}/validation",
    "GET /v1/research-runs/{job_id}/validation",
    "POST /v1/research-runs/{job_id}/finding",
    "GET /v1/research-runs/{job_id}/finding",
    "GET /v1/research-runs/{job_id}/report",
    "POST /v1/research-claims",
    "GET /v1/research-claims",
    "GET /v1/research-claims/{claim_id}",
    "GET /v1/research-claims/{claim_id}/evidence-graph",
    "GET /v1/claims/{claim_id}/evidence_graph",
    "GET /v1/findings",
    "DELETE /v1/workspaces/{workspace_id}",
    "GET /v1/workspaces/{workspace_id}/export",
    "POST /v1/research-claims/{claim_id}/plan-lock",
}

def main() -> int:
    text = CONTRACT.read_text(encoding="utf-8")
    documented = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- `") and "`" in stripped[3:]:
            value = stripped[3:stripped.index("`", 3)]
            if value.split(" ", 1)[0] in {"GET", "POST", "PUT", "PATCH", "DELETE"} and " /v1" in value:
                documented.add(value)
    actual: set[str] = set()
    for source in (ROOT / "researchos" / "saas").rglob("*.py"):
        if "tests" in source.parts:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                    continue
                path = decorator.args[0].value
                if isinstance(path, str) and path.startswith("/v1"):
                    actual.add(f"{method} {path}")
    if documented != EXPECTED:
        print("API_CONTRACT_V1 documentation drift:")
        print("missing:", sorted(EXPECTED - documented))
        print("extra:", sorted(documented - EXPECTED))
        return 1
    if actual != EXPECTED:
        print("FastAPI route-source drift:")
        print("missing:", sorted(EXPECTED - actual))
        print("extra:", sorted(actual - EXPECTED))
        return 1
    print(f"API contract PASS: {len(actual)} documented/route-source /v1 operations match")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())