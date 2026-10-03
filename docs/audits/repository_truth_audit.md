# Repository Truth Audit — Baseline

**Branch:** `fix/truth-audit-20260915`
**Base main:** `56b1f4f7939a0d4ef7a031870ddd954c75538781`
**Rule:** no claim is accepted without a verification command and recorded result.

| category | file | line | claim | verification command run | verification result | severity |
|---|---|---:|---|---|---|---|
| FABRICATED_CITATION | `docs/research/xauusd_m1_b_level_validation_record.md` | 1 | `artifacts/xauusd_m1_walkforward.json` was cited with SHA `0b97d63f...` | `git log --all --full-history -- artifacts/xauusd_m1_walkforward.json` | **EMPTY** in the user's cloned repository; GitHub path history also returned `[]`; current `main` path returns 404 | CRITICAL |
| ARTIFACT_CI_RECOVERY | `artifacts/xauusd_m1_walkforward.json` | — | historical artifact might be recoverable from CI | `GET /repos/bi421/ResearchOS/actions/runs?head_sha=f0b2c7596f24b7a8f4cc15f7dd53b609acb5205f` | two successful CI runs found: `34863940436`, `34858580239` | VERIFIED |
| ARTIFACT_CI_RECOVERY | `artifacts/xauusd_m1_walkforward.json` | — | inspect CI artifacts | `fetch_workflow_run_artifacts(run=34863940436)` and `fetch_workflow_run_artifacts(run=34858580239)` | both returned `artifacts: []`; no recoverable walk-forward artifact | CRITICAL |
| ARTIFACT_SOURCE_INTEGRITY | `artifacts/xauusd_m1_real_events_outcomes.json` | — | recorded source artifact exists | `GET /repos/bi421/ResearchOS/contents/artifacts/xauusd_m1_real_events_outcomes.json?ref=main` | **404 Not Found**; the recorded source artifact is also not currently committed on `main` | CRITICAL |
| STUB_EXPOSED_AS_PUBLIC_API | `researchos/macro/storage/__init__.py` | 6 | `JsonStore`/`ParquetStore` were public exports | `grep -nE 'JsonStore|ParquetStore' researchos/macro/storage/__init__.py` | exports came from `researchos.macro.storage.skeleton`; skeleton contains `TODO: Implement` and `NotImplementedError` | CRITICAL — FIXED on branch |
| SCOPE_GUARD_GAP | repository root | — | root-level scratch scripts were not covered by existing forbidden patterns | `python scripts/check_scope.py --base origin/main` + direct pattern inspection | existing patterns covered `_tmp`, `tmp_`, `scratch_`, `.bak`, pytest/ruff text, `FORENSIC_AUDIT`, `run_full_analysis`; named root scripts did not match | HIGH — FIXED prospectively on branch |
| TODO | `researchos/macro/storage/skeleton.py` | multiple | storage methods are implemented | `grep -nE 'TODO|NotImplementedError' researchos/macro/storage/skeleton.py` | `ParquetStore` and `JsonStore` write/read methods contain explicit `TODO: Implement` / `NotImplementedError` | HIGH — no longer public API |
| ENGINE_OWNERSHIP | `docs/CANONICAL_ENGINE.md` | — | duplicate `cpp_quant/` ownership remained unresolved | filesystem/path inspection against canonical ownership document | `cpp_quant/` is absent on current `main`; `cpp_quant_engine/` remains canonical | PASS |

## Fixed on branch

1. **Unimplemented storage skeletons removed from public API.** `researchos.macro.storage` now exports only `BaseStore`.
2. **Scope guard strengthened.** New/changed root-level `*.py` files are forbidden; legacy root scripts are reported separately instead of silently accepted.
3. **Evidence record corrected.** The walk-forward result is now explicitly `HISTORICAL ARTIFACT UNVERIFIED`; it is not represented as reproducible evidence.
4. **Truth-audit gate added.** `scripts/audit_repository_truth.py` produces a machine-readable audit process and a single markdown table with command + result per row.
5. **Regression tests added.** `tests/test_repository_truth_contract.py` locks the public-API, scope-guard, and evidence-record rules.
6. **CI enforcement added.** The Health Evidence job now runs `python scripts/audit_repository_truth.py`.

## Still open — intentionally not falsified away

**F07: walk-forward artifact recovery.** The exact artifact bytes have not been recovered. The two CI runs associated with the original gate implementation contained no workflow artifacts. Therefore the recorded numerical values cannot be upgraded to `VERIFIED` merely because a SHA is written in documentation.

The correct next action is artifact recovery from a reachable Git object, CI artifact, or other canonical evidence source. If recovery fails, the historical numerical record remains `UNVERIFIED` permanently and a new rerun must be labeled as a **new experiment**, not the missing original artifact.

## Scientific boundary

The historical Issue #50 record does **not** justify the claim `XAUUSD has no edge`. The defensible statement is: the recorded SMA20/SMA100 B-level validation did not satisfy the frozen acceptance contract, and its underlying walk-forward artifact is currently unverified.
