# HFT -> QROS read-only XAUUSD quote bridge V1

## Status

Implemented as a local JSON file handoff and strict parser on branch `feat/hft-readonly-feed-bridge`. This is a quote-snapshot integration only. It does not provide a continuous stream, historical candles, trade volume, provider sequence integrity, signal generation, persistent dataset registration, or order execution.

## Flow

1. HFT runs `tools/mt5_readonly_feed.py --timestamp-mode pepperstone-server`.
2. `tools/export_qros_quote.py` accepts only a successful read-only XAUUSD probe and writes an atomic JSON envelope with schema `qros.hft.xauusd.quote-snapshot.v1`, UTC event and ingest timestamps, bid/ask/spread, source identity and SHA-256 payload digest.
3. QROS `researchos.data_engine.hft_feed.load_hft_quote_snapshot()` checks schema, payload digest, provider identity, quote invariants, timezone-aware event/ingest times and current freshness. A snapshot older than the freshness limit is rejected at QROS ingestion even if the HFT probe passed when it was written.
4. The parsed object is immutable and explicitly reports `is_continuous_stream=False` and `sequence=None`. Consumers must not treat it as a complete event stream or OHLCV dataset.
5. `researchos.data_engine.hft_quote_adapter.snapshot_to_quote()` maps the validated snapshot into QROS's existing `Quote` domain object for quote-level consumers. It sets sizes to zero (unknown/unavailable), does not infer volume or trade side, and retains the original snapshot separately for lineage.
6. `researchos.evidence.hft_quote_emission.emit_hft_quote_snapshot()` emits the validated quote into QROS's existing append-only `EvidenceRepository` as a first-class `QuoteSnapshot` envelope with QROS artifact and lineage hashes. The repository must be supplied explicitly; persistence durability depends on which `ResearchRepository` it wraps. `tools/ingest_hft_quote_snapshot.py` provides a local SQLite persistence path under `.healthcheck/` and verifies the stored artifact after read-back. This evidence artifact is not automatically attached to a research run/report yet.

## Run locally

From PowerShell:

```powershell
Set-Location C:\Users\User\Desktop\HFT
python tools\export_qros_quote.py --output C:\Users\User\Desktop\QROS\.health\hft-xauusd-quote.json

Set-Location C:\Users\User\Desktop\QROS
.\.venv\Scripts\python.exe tools\ingest_hft_quote_snapshot.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_hft_feed_bridge.py tests\test_hft_quote_adapter.py tests\test_hft_quote_evidence.py
```

The `.health` file is local handoff evidence and must not be committed or used as a shared multi-tenant storage location. For a hosted QROS worker, replace the local file handoff with an authenticated service/queue contract and explicit tenant-scoped persistence.

## Safety boundaries

- Only `Pepperstone-Demo`/Pepperstone server quote data is accepted by this version; no credentials or account number are exported.
- The quote feed's healthy status is not proof of order-execution connectivity.
- No order, position, or account mutation API is called.
- No current snapshot is promoted to historical candle data.
- A SHA-256 digest detects accidental payload alteration; it is not a digital signature and does not authenticate a malicious producer.
- No live SaaS API, Supabase persistence, tenant context, worker, or research-run orchestration is wired by this local integration.

## Verification boundaries

The parser unit tests verify valid snapshots, tampering, provider/schema rejection, stale/future time rejection, quote invariants and sequence-claim rejection. A successful local handoff test proves only that this workstation can pass a fresh MT5 snapshot through the file contract; it does not prove production readiness or profitable trading edge.
