from __future__ import annotations

import logging
from uuid import uuid4

from researchos.saas.observability import actor_user_id_var, observe_error, tenant_id_var

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext
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


def test_unhandled_exception_emits_only_safe_structured_error_event(caplog) -> None:
    app = create_app(metrics_token="scrape-secret")

    @app.get("/test-unhandled-observability")
    def test_unhandled_observability() -> None:
        raise RuntimeError("password=super-secret-token")

    client = TestClient(app, raise_server_exceptions=False)
    caplog.set_level(logging.ERROR, logger="qros.saas")

    response = client.get(
        "/test-unhandled-observability",
        headers={"X-Request-ID": "obs-unhandled-123"},
    )

    assert response.status_code == 500
    structured_errors = [
        record.message
        for record in caplog.records
        if '"event":"qros_error"' in record.message
    ]
    assert len(structured_errors) == 1
    message = structured_errors[0]
    assert '"error_code":"internal_error"' in message
    assert '"request_id":"obs-unhandled-123"' in message
    assert "super-secret-token" not in message
    assert "unhandled request exception" not in caplog.text


def test_required_secret_classes_are_redacted() -> None:
    sanitized = sanitize_log_fields(
        {
            "Authorization": "Bearer jwt-secret",
            "jwt": "jwt-secret",
            "DATABASE_URL": "postgresql://user:secret@db.example/qros",
            "aws_secret_access_key": "aws-secret",
            "private_dataset_content": "private-market-data",
        }
    )

    assert all(value == "[REDACTED]" for value in sanitized.values())


def test_structured_error_contains_safe_correlation_context(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="qros.saas")
    tenant_token = tenant_id_var.set("tenant-safe")
    actor_token = actor_user_id_var.set("actor-safe")
    try:
        observe_error(
            severity="warning",
            error_code="forbidden",
            error=PermissionError("do not log this secret"),
            metadata={
                "method": "GET",
                "path": "/v1/private",
                "status_code": 403,
                "authorization": "Bearer should-not-appear",
                "private_dataset_content": "private-data",
            },
        )
    finally:
        tenant_id_var.reset(tenant_token)
        actor_user_id_var.reset(actor_token)

    message = caplog.records[-1].message
    assert '"event":"qros_error"' in message
    assert '"error_code":"forbidden"' in message
    assert '"tenant_id":"tenant-safe"' in message
    assert '"actor_user_id":"actor-safe"' in message
    assert "should-not-appear" not in message
    assert "private-data" not in message
    assert "do not log this secret" not in message


class _TestAuth:
    def __init__(self) -> None:
        self.context = TenantContext(uuid4(), uuid4(), Plan.PRO)

    def authenticate(self, authorization: str | None) -> TenantContext:
        return self.context


def test_validation_response_does_not_echo_submitted_secret() -> None:
    client = TestClient(create_app(auth_provider=_TestAuth()))
    secret = "submitted-secret-token"

    response = client.post(
        "/v1/research-runs",
        json={"dataset_version_id": secret},
    )

    assert response.status_code == 400
    assert secret not in response.text
    assert "input" not in response.json()["detail"][0]
