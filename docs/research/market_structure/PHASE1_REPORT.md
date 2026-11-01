# Market Structure Variant Study — Phase 1 Report

**Phase / Status:** Phase 1 — `BLOCKED` (draft SPEC/grid committed; effective pre-registration not accepted)
**Base commit:** `8e756c889003e4686e96fd20427b218f24f3b461`
**Draft SPEC/grid commit:** `5e8dc90e58c5c944774ecd2d92f6a1d3063bceab`
**Branch:** `feat/market-structure-variants`

## Goal

Write exact, reproducible Market Structure definitions, the full parameter grid, execution rules, costs, metrics, splits, and decision gates before any variant result is computed.

## Files created

- `docs/research/market_structure/SPEC.md`
- `docs/research/market_structure/grid.json`
- `docs/research/market_structure/PHASE1_REPORT.md`

## Commands run and literal outputs

```text
Get-FileHash docs/research/market_structure/grid.json -Algorithm SHA256
SHA256: e09001e1602cf5624e72ea35ab6c37a43db6a5fa3aa487705073cad81603726a

python -c JSON verification
variants=56
unique_keys=56
sha256=e09001e1602cf5624e72ea35ab6c37a43db6a5fa3aa487705073cad81603726a
bom=False

Get-Item SPEC.md,grid.json


git diff --check
DIFF_CHECK_EXIT=0
```

The final SPEC records the proposed 2025 UTC boundary, explicitly marking its slice hash unavailable and the boundary invalid as a fresh untouched holdout. After commit, the grid was reloaded as JSON: 56 variants, 56 unique keys, SHA-256 `e09001e1602cf5624e72ea35ab6c37a43db6a5fa3aa487705073cad81603726a`.

## Dataset and cost blockers

- QROS `data/curated/xauusd` does not exist in the current checkout.
- `data/mt5/xauusd/README.md` requires a versioned external dataset and fail-closed behavior when absent.
- No `.dvc/config`, `.dvc` dataset pointer, or installed `dvc` command was found.
- A prior audit reports 1,764,176 XAUUSD M1 rows and full-dataset SHA-256 `632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`; the bytes are not available to re-hash.
- Proposed 2025 OOS window: `2025-01-01T00:00:00Z` to `2025-12-31T23:59:59Z`; slice SHA-256 unavailable and the period was exposed in unrelated prior audits. It is not accepted as a fresh holdout.
- `config/costs.yaml` is `UNVERIFIED`; spread scenario 0.36 price units is explicitly not a verified historical average and excludes slippage/commission. Commission and slippage evidence is unavailable.
- The 500-row M15 CSV in `ForexCourse/mt5_audit_output` is not an approved frozen M1 dataset and is below the 1,245 observation gate; it was not used for variant evaluation.

## Acceptance status

- SPEC and grid drafts created: `PASS`.
- Grid enumerates 56 unique keys: `PASS`.
- Grid SHA reproduced after commit: `PASS` — `e09001e1602cf5624e72ea35ab6c37a43db6a5fa3aa487705073cad81603726a`.
- Effective locked holdout dataset hash and fresh boundaries: `BLOCKED`.
- Verified spread, commission, slippage evidence: `BLOCKED`.
- No Market Structure variant was run on market data: `PASS`.
- Effective Phase 1 pre-registration acceptance: `BLOCKED`.

## Deviations

The files are explicitly marked as a draft, not an effective pre-registration. The holdout slice hash and verified cost values were not fabricated. The draft grid retains the existing QROS detector's 56-definition axes; `choch_rule` and `trend_filter` are fixed constants, not additional axes. This differs from possible example axes in the user specification and is declared explicitly in `SPEC.md`.

## Open risks

1. Dataset bytes and immutable source manifest must be recovered and independently verified.
2. A genuinely unused chronological OOS slice must be selected and hashed before results.
3. Broker/account-specific spread, commission, and slippage evidence is required.
4. The future adapter must expose the opposite confirmed swing anchor for the stop rule.
5. The prior uncommitted detector worktree changes remain separate and untouched by this phase.

**Decision:** stop here. Do not start Phase 2 or compute variant results until the blockers are resolved and an effective pre-registration is committed.
