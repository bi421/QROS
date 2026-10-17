# Alternative-data research module (v1)

## Purpose and safety boundary

`researchos.orchestration.alternative_data_research` provides deterministic, offline research primitives for timestamped insider-transaction data. It is an additive module. It is not wired into the XAUUSD live decision engine and does not place or recommend trades. A cluster is a hypothesis candidate, not evidence of a profitable edge.

## Current implementation

- Immutable `InsiderTransaction` records with timezone-aware `event_at`, `usable_at`, and `retrieval_at` provenance.
- Transaction deduplication by source transaction ID; conflicting duplicate IDs fail closed.
- Suspicious same-ticker/date/code/amount batch detection. Findings are review flags, not proof of compensation.
- Point-in-time 60-day cluster screening; counts unique insiders, requires source-verified open-market purchase status, and excludes future-public data.
- Unknown/suspect batch records are excluded. Similar-amount groups are held for review unless the source record has an explicit `batch_status=CLEAR` after review.
- Benjamini-Hochberg correction uses the project's existing `statistical_validation.benjamini_hochberg` implementation. Adjusted p-values do not prove edge.
- `researchos.research_adapters.quiver_insider_api` fetches the documented Quiver live-insiders endpoint over HTTPS using a Bearer token, hashes and preserves the raw response, normalizes known fields, and reports rejected rows.
- `scripts/fetch_quiver_insiders.py` writes raw JSON, normalized CSV and a manifest. It reads `QUIVER_API_KEY` from the environment; the key is never accepted as a command-line argument or written to artifacts.
- `scripts/audit_alternative_data.py` runs the audit on a normalized CSV and emits JSON.

## Normalized CSV contract

Required columns:

`transaction_id,ticker,insider_id,transaction_code,event_at,usable_at,retrieved_at,amount_usd,source_ref,open_market_verified`

Optional column: `batch_status` (`UNKNOWN`, `SUSPECT`, `CONFIRMED_COMPENSATION`, `CLEAR`). Timestamps must be ISO-8601 and include a UTC offset. `open_market_verified` accepts true/false/unknown; unknown is rejected from cluster counts. `batch_status=CLEAR` must only be supplied after source-level review. The input data is not automatically verified by QROS.

Example:

```powershell
python scripts/audit_alternative_data.py `
  --input .\data\normalized_insider_transactions.csv `
  --as-of 2026-10-17T12:00:00+00:00 `
  --window-days 60 `
  --min-insiders 3 `
  --output .\artifacts\alternative-data-audit.json
```

## Quiver provider integration and current limits

With `QUIVER_API_KEY` configured securely in the process environment, fetch and preserve a response:

```powershell
python scripts/fetch_quiver_insiders.py `
  --raw-output .\artifacts\quiver-insiders-raw.json `
  --csv-output .\artifacts\quiver-insiders-normalized.csv `
  --manifest-output .\artifacts\quiver-insiders-manifest.json
```

Do not paste the API key into chat, commit it, or place it in a command-line argument.

The connector uses the documented HTTPS endpoint `https://api.quiverquant.com/beta/live/insiders` and `Authorization: Bearer ...` authentication, with the key read from `QUIVER_API_KEY`. The public endpoint example documents fields including `Ticker`, `Date`, `Name`, `AcquiredDisposedCode`, `TransactionCode`, `Shares`, `PricePerShare`, and `fileDate` (see https://api.quiverquant.com/datasets/insider-trades and https://api.quiverquant.com/docs/schema.json).

The connector preserves the exact response bytes and SHA-256, maps `Date` to event time and `fileDate` to the earliest usable-time candidate, and rejects rows with missing or inconsistent timestamps. It fetches one live endpoint response; pagination, complete historical backfill, vendor-side revision history, and plan entitlement have not been independently verified. A live authenticated request has not been run in this environment because no Quiver credential was available.

Critically, the documented sample schema does not contain an explicit open-market verification flag. SEC transaction code `P` alone is not sufficient to prove the purchase was open-market rather than private. Therefore `open_market_verified` remains `UNKNOWN` unless the provider response explicitly supplies an affirmative `openMarketVerified` field; the cluster screener then excludes that row. The connector can ingest and audit data without pretending this evidence gap is resolved.

## Validation still required before XAUUSD use

1. Verify vendor contract, field semantics, historical coverage, rate limits and actual timestamp availability.
2. Create a preregistered hypothesis and point-in-time data snapshot.
3. Define XAUUSD target horizon and null model before running the test.
4. Apply dependence-aware resampling, multiple-testing correction and out-of-sample/walk-forward validation.
5. Compare against a baseline and verify incremental value after realistic spread, commission, slippage and latency.
6. Store immutable input hashes, parameters, excluded-row reasons and full results in the QROS evidence artifact.

## Status vocabulary

- `IMPLEMENTED`: offline deterministic functions and CSV runner exist.
- `UNIT_TESTED`: only after the corresponding test run is observed to pass.
- `VENDOR_CONNECTOR_IMPLEMENTED`: endpoint/auth/parser code exists; mock-tested only.
- `VENDOR_LIVE_AUTH_VERIFIED`: not established because no real API credential/request was available.
- `EDGE_VALIDATED`: not established by this module.
- `XAUUSD_TRADING_APPROVED`: out of scope and never emitted by this module.
