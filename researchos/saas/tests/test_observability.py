from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.observability import RequestMetrics, StructuredRequestObserver, sanitize_log_fields


def test_request_correlation_is_echoed_and_observed(caplog) -> None:
    client = TestClient(create_app())
    caplog.set_level(logging.INFO, logger="qros.saas")

    response = client.get("/healthz", headers={"X-Request-ID": "obs-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "obs-123"
    assert client.app.state.observability.metrics.requests_total == 1
    assert any('"request_id":"obs-123"' in record.message for record in caplog.records)


def test_missing_request_id_is_generated_and_bounded() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert request_id
    assert len(request_id) <= 128
    assert client.app.state.observability.metrics.requests_total == 1


def test_metrics_exposition_is_prometheus_text_and_contains_no_tenant_data() -> None:
    client = TestClient(create_app())
    client.get("/healthz")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    assert "# TYPE qros_http_requests_total counter" in body
    assert "qros_http_requests_total 1" in body
    assert "qros_http_errors_total 0" in body
    assert "workspace_id" not in body


def test_sensitive_log_fields_are_redacted() -> None:
    sanitized = sanitize_log_fields(
        {
            "authorization": "Bearer secret",
            "api_key": "top-secret",
            "billing_signature": "sig",
            "normal": "safe",
        }
    )

    assert sanitized == {
        "authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "billing_signature": "[REDACTED]",
        "normal": "safe",
    }


def test_observer_records_5xx_as_error() -> None:
    metrics = RequestMetrics()
    observer = StructuredRequestObserver(metrics)

    observer.observe(
        request_id="failure",
        method="GET",
        path="/test",
        status_code=503,
        duration_ms=12.5,
    )

    snapshot = metrics.snapshot()
    assert snapshot["requests_total"] == 1
    assert snapshot["errors_total"] == 1
    assert snapshot["status_counts"] == {503: 1}
