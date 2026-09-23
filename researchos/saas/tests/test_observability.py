from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi.testclient import TestClient

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.api import create_app
from researchos.saas.observability import RequestMetrics, StructuredRequestObserver, emit_log, sanitize_log_fields
from researchos.saas.queue import InMemoryResearchJobQueue
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker


def test_request_correlation_is_echoed_and_observed_as_json(caplog) -> None:
    app = create_app(metrics_token="scrape-secret")
    client = TestClient(app)
    caplog.set_level(logging.INFO, logger="qros.saas")

    response = client.get("/healthz", headers={"X-Request-ID": "obs-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "obs-123"
    records = [json.loads(record.message) for record in caplog.records if record.name == "qros.saas"]
    assert records
    required = {"timestamp", "level", "request_id", "tenant_id", "job_id", "message", "duration_ms"}
    assert required <= records[-1].keys()
    assert records[-1]["request_id"] == "obs-123"


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


def test_emit_log_is_json_parseable(caplog) -> None:
    caplog.set_level(logging.INFO, logger="qros.saas")
    emit_log(level=logging.INFO, message="contract-test", request_id="req-1")
    record = next(r for r in caplog.records if r.name == "qros.saas")
    payload = json.loads(record.message)
    assert payload["request_id"] == "req-1"
    assert payload["message"] == "contract-test"
    assert {"timestamp", "level", "request_id", "tenant_id", "job_id", "message", "duration_ms"} <= payload.keys()
