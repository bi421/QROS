# FTMO-Demo XAUUSD M1 — Dataset Card

**Dataset ID:** `FTMO_DEMO_XAUUSD_M1_2021_2026_V1`
**Status:** `LOCAL BYTE-INTEGRITY PASS; EXECUTION-COST MODEL NOT CERTIFIED`
**Acquired:** 2026-11-01 UTC
**Instrument:** XAUUSD CFD feed, M1
**Source server:** FTMO-Demo (MetaTrader 5)

## Provenance

The data was acquired from the connected MetaTrader 5 terminal using `scripts/acquisition/mt5_xauusd_m1.py`. The terminal reported company `FTMO Global Markets Ltd`, build `6292`, `maxbars=5,000,000`; symbol metadata was digits `2`, point/tick size `0.01`, contract size `100`. No account identifier was recorded.

FTMO states its services are simulated trading and that its technical solution and data feed are powered by liquidity providers; FTMO does not act as a broker. Therefore this is one FTMO simulated XAUUSD feed, not a centralized or broker-agnostic global spot-gold tape.

## Coverage and hashes

- Requested: `2021-01-01T00:00:00Z` through `2026-10-31T23:59:59Z`.
- Actual: `2021-01-01T00:00:00Z` through `2026-10-30T23:49:00Z`.
- `2,046,268` rows; `70` monthly CSV files; `105,739,421` bytes across the 73 local files (70 CSV + 3 metadata/audit JSON files).
- Concatenated raw monthly CSV bytes SHA-256: `e63acae2c39ff2b14538c1a3e696aa9e90da59274e4ca6184c1542dc5b812c06`.
- Inventory SHA-256: `44c9ceef74bad2a40ffb50ea246f10bbf4e3cc3455b6f4f4698c81f1b3a8fb11`.
- Acquisition manifest SHA-256: `f756e2721f5d272c3dd09a60f69f37887ffc653d20aff35c11c64336912810bf`.
- Source context SHA-256: `8115cdc76e400da5027f72bc357ec66cea0014aa9aa177630e76913677eca060`.
- Independent audit JSON SHA-256: `63c31451806d510e8eb01902a9df39609e7de70727117cb14c8491da7edbd389`.

| Year | Rows | First observed UTC | Last observed UTC |
|---|---:|---|---|
| 2021 | 351,265 | 2021-01-01 00:00 | 2021-12-31 23:49 |
| 2022 | 350,345 | 2022-01-03 01:05 | 2022-12-30 23:49 |
| 2023 | 349,508 | 2023-01-03 01:05 | 2023-12-29 23:49 |
| 2024 | 352,105 | 2024-01-02 01:05 | 2024-12-31 23:49 |
| 2025 | 350,687 | 2025-01-02 01:05 | 2025-12-31 23:49 |
| 2026 | 292,358 | 2026-01-02 01:05 | 2026-10-30 23:49 |

## Structural audit

Reproducible command:

```powershell
py -3 scripts/audit_mt5_monthly_dataset.py data/raw/mt5/ftmo_demo_xauusd_2021_2026
```

Result: `INTEGRITY_PASS=True`.

- All 70 manifest chunk SHA-256 values and row counts matched.
- Timestamp parse failures, out-of-range rows, duplicates, non-increasing timestamps: `0`.
- Invalid OHLC, negative tick volume, negative real volume, negative spread: `0`.
- Gaps greater than 60 seconds: `1,917`; 368 are 60–300s, 28 are 301–900s, 1,213 are 901–21,600s, and 308 exceed 21,600s. Maximum observed gap: `263,760s`. These are observed gaps; the audit does not assume every gap is missing data or classify all of them as market closures. No synthetic bars were inserted.

## Spread observations

The MQL5 `MqlRates` structure contains an integer `spread` field; MetaTrader 5 Market Watch documentation defines spread in points. With point size `0.01`, the observed values are:

- Median: `15` points = `0.15` price units.
- 95th percentile: `47` points = `0.47` price units.
- Maximum: `1,718` points = `17.18` price units.
- Zero-spread rows: `34,022`.
- Rows above 100 points: `1,318`; above 500 points: `12`.

Do not interpret a zero value as free execution or clip extreme spreads. The M1 spread field is not tick-level executable bid/ask history and does not, by itself, model FTMO volume-band fills.

## Cost evidence

FTMO's 25 Sep 2025 trading update states Metals CFD commission changed to `0.0007%` of volume per side effective 29 Sep 2025 (previously `0.0005%`). FTMO's 16 Apr 2026 update says volume bands were extended to all active accounts, Challenges, Verifications, and Free Trials from 20 Apr 2026. The exact XAUUSD size tiers and account-specific realized commission have not been reconciled. Historical slippage is not measurable from OHLC bars. Therefore cost status remains `DOCUMENTED_NOT_ACCOUNT_VERIFIED` for commission and `UNVERIFIED` for slippage; `config/costs.yaml` remains unchanged and `UNVERIFIED`.

## Research split and contamination controls

- 2021–2025: development only; this period has prior QROS XAUUSD research exposure.
- 2026-01 through 2026-10: exploratory diagnostics only; prior M15 research already evaluated through 2026-10-14, so this is not fresh confirmatory OOS.
- Prospective study-locked OOS: 2026-11-02 through 2027-04-30 UTC; future data, hash pending until the interval closes. Do not access it for feature/parameter selection or debugging.
- No Market Structure variant has been run on this dataset.

## Storage and preservation

Local directory: `data/raw/mt5/ftmo_demo_xauusd_2021_2026/`. The whole `data/` tree is Git-ignored; the raw data is not committed. DVC is not configured and the QROS Staging `qros-datasets` bucket contained zero objects when checked. This is a local-only copy without a remote immutable backup. Preserve it as-is; any future acquisition must use a new versioned directory rather than overwrite these files.

## Source references

- MQL5 `MqlRates`: https://www.mql5.com/en/docs/constants/structures/mqlrates
- MetaTrader 5 Market Watch (spread in points): https://www.metatrader5.com/en/terminal/help/trading/market_watch
- FTMO Trading Update, 25 Sep 2025 (Metals CFD commission): https://ftmo.com/en/blog/trading-updates/trading-update-25-sep-2025/
- FTMO Trading Update, 16 Apr 2026 (volume bands extended to all accounts): https://ftmo.com/en/blog/trading-updates/trading-update-16-apr-2026/
- FTMO simulated-trading/data-feed disclosure: https://ftmo.com/en/symbols/
