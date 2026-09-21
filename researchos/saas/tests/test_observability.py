from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.observability import RequestMetrics, StructuredRequestObserver, sanitize_log_fields


def test_request_correlation_is_echoed_and_observed(caplog) -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)
    caplog.set_level(logging.INFO, logger="qros.saas")

    response = client.get("/healthz", headers={"X-Request-ID": "obs-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "obs-123"
    assert app.state.observability.metrics.requests_total == 1
    assert any('"request_id":"obs-123"' in record.message for record in caplog.records)


def test_missing_request_id_is_generated_and_bounded() -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)

    response = client.get("/healthz")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert request_id
    assert len(request_id) <= 128
    assert app.state.observability.metrics.requests_total == 1


def test_metrics_endpoint_fails_closed_without_configuration() -> None:
    client = TestClient(create_app())

    response = client.get("/metrics")

    assert response.status_code == 503


def test_metrics_endpoint_requires_token_and_exposes_only_metrics() -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)
    client.get("/healthz")

    assert client.get("/metrics").status_code == 404
    response = client.get("/metrics", headers={"X-Metrics-Token": "scrape-secret"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    assert "# TYPE qros_http_requests_total counter" in body
    assert "qros_http_requests_total 2" in body
    assert "qros_http_errors_total 0" in body
    assert "workspace_id" not in body
    assert "scrape-secret" not in body


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


def test_5xx_emits_structured_error_event(caplog) -> None:
    metrics = RequestMetrics()
    observer = StructuredRequestObserver(metrics)
    caplog.set_level(logging.ERROR, logger="qros.saas")

    observer.observe(
        request_id="failure-123",
        method="POST",
        path="/v1/research-runs",
        status_code=503,
        duration_ms=12.5,
    )

    assert any(
        '"event":"http_request_error"' in record.message
        and '"request_id":"failure-123"' in record.message
        and '"status_code":503' in record.message
        for record in caplog.records
    )
    assert all("secret" not in record.message.lower() for record in caplog.records)


def test_request_id_control_characters_are_neutralized() -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)

    response = client.get("/healthz", headers={"X-Request-ID": "safe\nrequest\r\tid"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "safe-request--id"


def test_unhandled_exception_is_counted_as_5xx() -> None:
    app = create_app(metrics_token="scrape-secret")

    @app.get("/test-unhandled")
    def test_unhandled() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-unhandled")

    assert response.status_code == 500
    snapshot = app.state.observability.metrics.snapshot()
    assert snapshot["requests_total"] == 1
    assert snapshot["errors_total"] == 1
    assert snapshot["status_counts"] == {500: 1}
