# QROS SaaS container deployment

## Canonical deployment artifact

QROS uses the FastAPI production composition root at
`researchos.saas.runtime:app`. It requires:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-only; never expose it to a browser)
- `BILLING_WEBHOOK_SECRET` for the billing webhook

The repository contains a production-oriented `Dockerfile` and a
`docker-compose.yml` for local container validation.

## Local validation

1. Copy `.env.example` to `.env`.
2. Put real development/staging Supabase credentials in `.env`.
3. Run:

```bash
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/healthz
```

The compose file intentionally does not create a second PostgreSQL database.
Supabase is the canonical persistence layer, and the versioned
`supabase/migrations/` directory is the canonical schema migration system.

## Production boundary

The Docker image does not contain secrets. Secrets must be injected by the
deployment platform/runtime secret store.

The image runs as the unprivileged `nobody` user, drops Linux capabilities,
uses a read-only root filesystem, and exposes only the FastAPI HTTP port.

Before production release, execute the full migration set against the target
Supabase project and verify `/readyz`, authentication, tenant isolation,
dataset persistence, research execution, claims, evidence, and billing.

A successful image build is not a production deployment.
