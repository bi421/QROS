#!/usr/bin/env python3
"""Verify the executable FastAPI /v1 surface matches API_CONTRACT_V1.md."""

from __future__ import annotations

import re
from pathlib import Path

from researchos.saas.api import create_app

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
    "GET /v1/research-runs/{job_id}/result",
    "GET /v1/research-runs/{job_id}/evidence",
    "GET /v1/research-runs/{job_id}/report",
    "POST /v1/research-claims",
    "GET /v1/research-claims",
    "GET /v1/research-claims/{claim_id}",
    "GET /v1/research-claims/{claim_id}/evidence-graph",
    "POST /v1/research-claims/{claim_id}/plan-lock",
}

def main() -> int:
    text = CONTRACT.read_text(encoding="utf-8")
    documented = set(re.findall(r"- `((?:GET|POST|PUT|PATCH|DELETE)) (/v1[^` ]*)`", text))
    documented = {f"{method} {path}" for method, path in documented}
    app = create_app()
    actual = {
        f"{method.upper()} {path}"
        for path, item in app.openapi()["paths"].items()
        if path.startswith("/v1")
        for method in item
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    if documented != EXPECTED:
        print("API_CONTRACT_V1 documentation drift:")
        print("missing:", sorted(EXPECTED - documented))
        print("extra:", sorted(documented - EXPECTED))
        return 1
    if actual != EXPECTED:
        print("FastAPI/OpenAPI drift:")
        print("missing:", sorted(EXPECTED - actual))
        print("extra:", sorted(actual - EXPECTED))
        return 1
    print(f"API contract PASS: {len(actual)} documented/executable /v1 operations match")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())