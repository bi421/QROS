from __future__ import annotations

import json
import logging
from uuid import uuid4

from researchos.saas.observability import actor_user_id_var, observe_error, tenant_id_var

from fastapi.testclient import TestClient

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.api import create_app
from researchos.saas.queue import InMemoryResearchJobQueue
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker
from researchos.saas.contracts import Plan, TenantContext
from researchos.saas.observability import RequestMetrics, StructuredRequestObserver, sanitize_log_fields


def test_request_correlation_is_echoed_and_observed_as_json(caplog) -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)
    caplog.set_level(logging.INFO, logger="qros.saas")

    response = client.get("/healthz", headers={"X-Request-ID": "obs-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "obs-123"
    records = [json.loads(record.message) for record in caplog.records if record.name == "qros.saas"]
    observed = [record for record in records if record.get("event") == "http_request_completed"]
    assert observed
    assert observed[-1]["request_id"] == "obs-123"
    assert {
        "event",
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
    } <= observed[-1].keys()


def test_missing_request_id_is_generated_and_bounded() -> None:
    app = create_app(metrics_token="scrape-secret")
    response = TestClient(app).get("/healthz")
    request_id = response.headers["X-Request-ID"]

    assert response.status_code == 200
    assert request_id
    assert len(request_id) <= 128


def test_metrics_endpoint_exposes_required_counters() -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)
    client.get("/healthz")

    response = client.get("/metrics", headers={"X-Metrics-Token": "scrape-secret"})

    assert response.status_code == 200
    body = response.text
    assert "jobs_created_total 0" in body
    assert "jobs_failed_total 0" in body
    assert "tenant_isolation_violations_total 0" in body


def test_metrics_endpoint_fails_closed_without_configuration() -> None:
    assert TestClient(create_app()).get("/metrics").status_code == 503


def test_sensitive_log_fields_are_redacted() -> None:
    sanitized = sanitize_log_fields({
        "authorization": "Bearer secret",
        "api_key": "top-secret",
        "billing_signature": "sig",
        "normal": "safe",
    })
    assert sanitized == {
        "authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "billing_signature": "[REDACTED]",
        "normal": "safe",
    }


def test_worker_log_preserves_request_id_for_same_job(caplog) -> None:
    workspace_id = uuid4()
    job_id = uuid4()
    request_id = "api-request-456"
    metrics = RequestMetrics()
    observer = StructuredRequestObserver(metrics)

    class Executor:
        def execute(self, received_job_id):
            assert received_job_id == job_id
            return ResearchResult(
                status="SUCCEEDED",
                source_dataset_sha256="0" * 64,
                artifacts=(ResearchArtifact("artifact-1", "evidence", "1" * 64),),
            )

    # The queue retains the API correlation ID alongside the durable job ID.
    queue = InMemoryResearchJobQueue()
    queue.enqueue(workspace_id, job_id, request_id=request_id)
    assert queue.request_ids[job_id] == request_id

    store = InMemoryResearchJobStore()
    from researchos.saas.contracts import ResearchJob, ResearchJobStatus
    store.create(workspace_id, ResearchJob(
        id=job_id,
        workspace_id=workspace_id,
        dataset_version_id=uuid4(),
        workflow_id="xauusd_m1_frozen_research_v1",
        status=ResearchJobStatus.QUEUED,
        source_dataset_sha256="0" * 64,
    ))
    caplog.set_level(logging.INFO, logger="qros.saas")

    ResearchWorker(store, Executor(), observability=observer).run_queued_message({
        "workspace_id": str(workspace_id),
        "research_run_id": str(job_id),
        "request_id": request_id,
    })

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "qros.saas"
    ]
    assert records
    job_records = [r for r in records if r["job_id"] == str(job_id)]
    assert job_records
    assert all(r["request_id"] == request_id for r in job_records)
    assert all({"timestamp", "level", "request_id", "tenant_id", "job_id", "message", "duration_ms"} <= r.keys() for r in job_records)


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
