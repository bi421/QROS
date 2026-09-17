# XAUUSD M1 B-Level Validation — Evidence Record

**Document type:** Reproducible scientific evidence record
**Issue:** #50 — B-level XAUUSD M1 edge validation gate
**Scientific scope:** probabilistic forecast-improvement validation only; no profitability or execution claim.

> **EVIDENCE INTEGRITY NOTICE — 2026-09-15**
>
> The recorded walk-forward SHA below is **not currently artifact-verified**. `artifacts/xauusd_m1_walkforward.json` is not present on `main`, and `git log --all --full-history -- artifacts/xauusd_m1_walkforward.json` returns an empty result. GitHub path history also returns no commits for that path. Therefore the numerical values in this historical record remain **RECORDED / UNVERIFIED**, not canonical verified evidence, until the exact artifact bytes are recovered from a reachable Git object or CI artifact and its SHA-256 is recomputed.

## 1. Frozen B-level acceptance contract

| Gate | Required | Historical recorded value | Historical result |
|---|---:|---:|---|
| Unique OOS events | >= 10,000 | 22,500 | PASS (recorded) |
| Aggregate Brier improvement | > 0 | +0.0009763019999999845 | PASS (recorded) |
| 95% fold-improvement CI lower bound | > 0 | +0.0001630058955555544 | PASS (recorded) |
| Paired permutation p-value | < 0.01 | 0.015009849901500985 | FAIL |
| Two-sided sign-test p-value | < 0.05 | 0.765991824244793 | FAIL |
| Positive fold rate | >= 70% | 24 / 45 = 53.33333333333333% | FAIL |
| Independent walk-forward audit | PASS | PASS (recorded) | UNVERIFIED until artifact recovery |
| Independent source-to-result audit | PASS | PASS (recorded) | UNVERIFIED until artifact recovery |
| Label-shuffle negative control | PASS | PASS (recorded) | UNVERIFIED until artifact recovery |
| Temporal-leakage negative control | PASS | PASS (recorded) | UNVERIFIED until artifact recovery |
| **Final B-level status** | **all gates PASS** | **NO_EDGE_OR_INCONCLUSIVE** | **NOT A B-LEVEL EDGE** |

The frozen thresholds remain unchanged: minimum 10,000 unique OOS events, positive aggregate Brier improvement, 95% CI lower bound > 0, paired permutation p < 0.01, two-sided sign-test p < 0.05, and >=70% improving folds, plus the independent audits and negative controls.

## 2. Historical numerical record — provenance status corrected

The historical walk-forward record reported:

- OOS unique validation events: **22,500**
- folds: **45**
- aggregate model Brier: **0.2490280668**
- aggregate baseline Brier: **0.2500043688**
- aggregate Brier improvement: **+0.0009763019999999845**
- positive folds: **24**
- negative folds: **21**
- positive fold rate: **53.33333333333333%**
- 95% fold-improvement CI: **[0.0001630058955555544, 0.0018529022222222228]**
- paired permutation p-value: **0.015009849901500985**
- two-sided sign-test p-value: **0.765991824244793**

These values are retained as **historical recorded values**. They must not be presented as independently reproducible evidence until the underlying walk-forward artifact is recovered and its bytes are verified against the recorded SHA.

## 3. Artifact provenance

### Source event artifact

`artifacts/xauusd_m1_real_events_outcomes.json`

Recorded SHA-256:

`8a2ba847da994dc0f570b7d63bdae3ff7d976d87260ff0f533a83b26079843e4`

### Walk-forward artifact

`artifacts/xauusd_m1_walkforward.json`

Recorded SHA-256:

`0b97d63f7963d1c26bb12e16d6fb66b73b901ebf4bc82adf6d628bb311d8d41c`

**Current verification:**

```text
Command: git log --all --full-history -- artifacts/xauusd_m1_walkforward.json
Output: <EMPTY>
Conclusion: the target artifact is not present in reachable local Git history.
```

The same path was checked against GitHub path history and returned no commits. A recorded SHA without recoverable artifact bytes is not sufficient evidence.

## 4. Failure register

| ID | Failure | Technical meaning | Scientific meaning | Status |
|---|---|---|---|---|
| F01 | Direct gate import failed with `ModuleNotFoundError: No module named 'scripts'` | CLI execution defect | None | Repaired |
| F02 | B-level gate exit code 2 | Acceptance criteria were not all satisfied | Historical result was not a validated B-level edge | Recorded |
| F03 | Permutation p = 0.015009849901500985 | Above 0.01 threshold | Significance gate failed | Recorded |
| F04 | Sign-test p = 0.765991824244793 | Above 0.05 threshold | Cross-fold consistency gate failed | Recorded |
| F05 | Positive fold rate = 53.33333333333333% | Below 70% threshold | Cross-fold consistency gate failed | Recorded |
| F06 | Nested discovery selected candidate failed outer minimum | Discovery implementation did not record insufficient OOS support | Not scientific edge evidence | Repaired in PR #61 |
| **F07** | **Walk-forward artifact cited by SHA but absent from reachable Git history** | **Evidence record cannot currently be reproduced from the cited artifact** | **Historical numerical result is UNVERIFIED** | **OPEN — artifact recovery required** |
| F08 | Root-level scratch/utility Python files are not covered by existing scope rules | Scope guard did not detect those names | Repository hygiene / reproducibility risk | Fixed prospectively; legacy files remain listed for review |
| F09 | `researchos.macro.storage.__init__` exported `ParquetStore` and `JsonStore` from `skeleton.py` | Unimplemented storage classes were public API | Silent data-loss risk if called | Fixed |

## 5. Correct scientific boundary

The historical Issue #50 execution does **not** justify the statement “XAUUSD has no edge.” The defensible statement is narrower:

> The recorded SMA20/SMA100 B-level validation did not satisfy the frozen B-level acceptance contract. Its underlying walk-forward artifact is currently unverified, so the numerical record must remain a historical, unverified record until the artifact is recovered.

No new hypothesis, regime decomposition, or frozen confirmation should be promoted as canonical B-level evidence until F07 is closed with an exact artifact and recomputed SHA-256.

## 6. Evidence-contract rule going forward

Every material operation must have a reconstructable chain:

`USER ACTION → COMMAND/API → INPUT SNAPSHOT → GIT SHA → DATASET HASH → EXACT OPERATION → OUTPUT ARTIFACT → VALIDATION/TEST → RESULT → SCIENTIFIC INTERPRETATION → NEXT ACTION`

A prose claim, CI-green badge, or recorded SHA alone is never sufficient.

**Required state vocabulary:**

- `SUCCESS` / `FAILURE` = engineering operation outcome.
- `VERIFIED` / `UNVERIFIED` = evidence integrity state.
- `B_LEVEL_PASS` / `NO_EDGE_OR_INCONCLUSIVE` = scientific conclusion.

A successful engineering operation never implies a scientific edge.

## 7. Authoritative current conclusion

**Current authoritative state:**

`NO_EDGE_OR_INCONCLUSIVE — HISTORICAL ARTIFACT UNVERIFIED`

The artifact-integrity failure is now explicitly part of the evidence history. It must be resolved by recovering the exact bytes from Git/CI evidence, hashing them, and recording the recovery command, source/run, SHA-256, and verification result. It must not be repaired by inventing or regenerating a replacement artifact and calling it the original result.
