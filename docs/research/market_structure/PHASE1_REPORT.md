# Market Structure Variant Study — Phase 1 Report

**Phase / Status:** `DRAFT ACCEPTED FOR STRUCTURAL IMPLEMENTATION; MARKET-DATA EXECUTION BLOCKED`
**Base commit:** `8e756c889003e4686e96fd20427b218f24f3b461`
**Initial Phase 1 SPEC/grid commit:** `5e8dc90e58c5c944774ecd2d92f6a1d3063bceab`
**Previous report commit:** `f9daf51858179e4277fa383cf383e943ffc841a5`
**Branch:** `feat/market-structure-variants`

## Goal

Freeze the 56-definition Market Structure hypothesis family, acquire a broker-specific XAUUSD M1 development dataset, verify its byte integrity, and define chronological development/walk-forward/future-OOS boundaries before any variant result is computed.

## Files created or updated

- `docs/research/market_structure/SPEC.md` — updated dataset identity, split hashes, cost evidence, and phase gates.
- `docs/research/market_structure/grid.json` — unchanged, 56 unique variants.
- `docs/research/market_structure/DATASET_CARD.md` — source, provenance, audit, spread/cost caveats, and storage limits.
- `docs/research/market_structure/PHASE1_REPORT.md` — this report.
- `scripts/audit_mt5_monthly_dataset.py` — reproducible independent monthly-file auditor.
- `tests/unit/test_audit_mt5_monthly_dataset.py` — synthetic integrity/fail-closed tests.

Raw data remains local and Git-ignored under `data/raw/mt5/ftmo_demo_xauusd_2021_2026/`; it is not committed.

## Acquisition evidence

Read-only terminal probe confirmed MT5 build `6292`, `maxbars=5,000,000`, server `FTMO-Demo`, symbol `XAUUSD`, point `0.01`, contract size `100`. Small history probes returned M1 bars in Jan 2021, Dec 2025, and Oct 2026.

Acquisition command:

```powershell
py -3 scripts/acquisition/mt5_xauusd_m1.py --start 2021-01-01 --end 2026-10-31 --output-dir data/raw/mt5/ftmo_demo_xauusd_2021_2026 --retries 5 --retry-delay 2
```

Observed result: exit `0`; 70 monthly chunks; `2,046,268` rows; actual range `2021-01-01T00:00:00Z` through `2026-10-30T23:49:00Z`. The source is the FTMO-Demo simulated feed; it is not represented as a centralized global gold tape or equivalent to the earlier unverified 1,764,176-row dataset.

## Dataset hashes

- Concatenated monthly CSV bytes SHA-256: `e63acae2c39ff2b14538c1a3e696aa9e90da59274e4ca6184c1542dc5b812c06`.
- Inventory SHA-256: `44c9ceef74bad2a40ffb50ea246f10bbf4e3cc3455b6f4f4698c81f1b3a8fb11`.
- `manifest.json`: `f756e2721f5d272c3dd09a60f69f37887ffc653d20aff35c11c64336912810bf`.
- `source_context.json`: `8115cdc76e400da5027f72bc357ec66cea0014aa9aa177630e76913677eca060`.
- `independent_audit.json`: `63c31451806d510e8eb01902a9df39609e7de70727117cb14c8491da7edbd389`.
- Development 2021–2025: `1,753,910` rows; raw-slice SHA-256 `e2e754cabf133436f91b0592aaf7b9a1d9161037171355ffcb0357f2fe77a507`.
- Exploratory 2026-01–2026-10: `292,358` rows; raw-slice SHA-256 `f5bc8c6aca03a3e6c0ab7c21e68bddb4f493074e6423e0feb0b3842ec7feccd0`.

## Independent audit and code checks

Command:

```powershell
py -3 scripts/audit_mt5_monthly_dataset.py data/raw/mt5/ftmo_demo_xauusd_2021_2026
```

Literal result: `INTEGRITY_PASS=True`; all 70/70 chunk hashes and row counts matched; timestamp parse failures `0`; out-of-range rows `0`; duplicate timestamps `0`; non-increasing intervals `0`; invalid OHLC `0`; negative tick volume, real volume, or spread `0`. There are `1,917` timestamp gaps greater than 60 seconds, retained and reported rather than repaired or silently dropped.

Spread field diagnostics: median 15 points (`0.15` price units), 95th percentile 47 points (`0.47`), max 1,718 points (`17.18`); 34,022 zero-spread rows; 1,318 rows above 100 points. These are not interpreted as guaranteed executable bid/ask costs.

Focused tests:

```text
py -3 -m pytest -q tests/unit/test_audit_mt5_monthly_dataset.py
4 passed in 0.97s

py -3 -m ruff check scripts/audit_mt5_monthly_dataset.py tests/unit/test_audit_mt5_monthly_dataset.py
All checks passed!

py -3 -m pytest -q tests/unit/test_audit_mt5_monthly_dataset.py
4 passed

git diff --check
DIFF_CHECK_EXIT=0
```

No full repository test suite was run in this phase.

## Cost and holdout decisions

- FTMO's published Metals CFD commission change to `0.0007%` per volume per side from 29 Sep 2025 is documented; the prior rate was `0.0005%`.
- FTMO says volume-band execution was extended to all active accounts, Challenges, Verifications, and Free Trials from 20 Apr 2026. Exact XAUUSD tiers and account-level realized commission are not verified.
- Historical slippage is not recoverable from M1 OHLC bars; no verified slippage evidence exists. `config/costs.yaml` was not modified and remains `UNVERIFIED`.
- 2021–2025 has prior QROS research exposure and is development-only. 2026-01–2026-10 is exploratory only because previous M15 research used this period.
- Prospective study-locked OOS is fixed at `2026-11-02T00:00:00Z` through `2027-04-30T23:59:59Z`; data/hash are pending until that future period closes.
- QROS Staging `qros-datasets` bucket had zero objects; no DVC remote is configured. Raw dataset is local-only, Git-ignored, and not backed by a remote immutable store.

## Acceptance status

- 56-variant grid, unique keys, and grid SHA: `PASS`.
- FTMO-Demo dataset acquisition and local byte integrity: `PASS`.
- Development/walk-forward raw slice identities and future OOS date boundary: `PASS` (future OOS hash pending by design).
- Account-specific XAUUSD volume-band and commission reconciliation: `BLOCKED`.
- Slippage model/evidence: `BLOCKED`.
- Remote immutable storage/backup: `BLOCKED`.
- Market Structure variants run on market data: `NO — NOT AUTHORIZED`.

## Decision

Phase 1 is accepted for structural implementation and synthetic detector testing only. Market-data execution remains blocked until the account-specific cost model is evidenced and the prospective OOS interval is collected, hashed, and locked. The next permitted implementation work is Phase 2 immutable definition and Phase 3 detector with synthetic fixtures only. No strategy is declared profitable; no candidate result exists.
