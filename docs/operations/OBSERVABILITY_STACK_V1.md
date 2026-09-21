# QROS Observability Stack V1

## Implemented application boundary

QROS exposes process-local Prometheus metrics from the authenticated `/metrics` surface and structured request logs with bounded correlation IDs. Sensitive credential-like fields are redacted before logging.

Core metrics:
- `qros_http_requests_total`
- `qros_http_errors_total`
- `qros_http_request_duration_ms`

Health:
- `/healthz`
- `/readyz`

## Prometheus

`ops/prometheus/alerts.yml` contains production alert rules for:
- sustained HTTP 5xx rate;
- sustained 5xx error bursts;
- HTTP p95 latency;
- unavailable QROS scrape target.

The QROS target must be configured in the deployment's Prometheus scrape configuration. The metrics endpoint requires the configured `X-Metrics-Token`; do not expose it publicly.

## Grafana

`ops/grafana/qros-dashboard.json` provides the baseline dashboard panels. Provisioning the dashboard and datasource is deployment work and requires environment-specific Prometheus connectivity.

## Error tracking

QROS emits structured request completion/error events. A third-party collector (OpenTelemetry/Sentry/etc.) may consume the application logs in the deployment environment; no credential or provider dependency is hard-coded into the application.

## Release gates

Configuration committed here is not evidence that monitoring is live. The production gate requires:
1. Prometheus successfully scraping the target.
2. Grafana successfully querying Prometheus.
3. Alert rules loaded and firing in a controlled test.
4. Health endpoints observed from the monitoring network.
5. A real incident event correlated by request ID.

Do not mark these gates complete from repository configuration alone.
