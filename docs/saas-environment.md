# ResearchOS SaaS environment contract

The application reads runtime configuration from environment variables. Secrets are never committed to the repository.

## Required in production

- `RESEARCHOS_ENV=production`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — server-only; never expose to browsers.

## Optional production settings

- `RESEARCHOS_SERVICE_NAME` (default: `researchos-saas`)
- `RESEARCHOS_LOG_LEVEL` (default: `INFO`)
- `RESEARCHOS_REQUEST_TIMEOUT_SECONDS` (default: `60`)
- `RESEARCHOS_MAX_REQUEST_BODY_BYTES` (default: `10000000`)
- `RESEARCHOS_REQUEST_ID_MAX_LENGTH` (default: `128`)
- `RESEARCHOS_RATE_LIMIT_PER_MINUTE` (default: `60`)
- `SUPABASE_PUBLISHABLE_KEY` — intended for a public frontend, not for server-side authorization.

## Security rules

1. Store production secrets only in the deployment platform's secret manager.
2. Never put the Supabase service-role key in frontend code, `NEXT_PUBLIC_*`, browser storage, or logs.
3. Never use user-editable profile metadata as an authorization source.
4. Production API documentation is disabled by default.
5. Tenant authorization is enforced server-side and by database RLS.
6. Any production deployment must pass the SaaS CI/security gates before release.
