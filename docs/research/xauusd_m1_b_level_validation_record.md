# XAUUSD M1 B-Level Validation — Evidence Record

**Document type:** Reproducible scientific evidence record

**Scope:** XAUUSD M1 probabilistic forecast-improvement validation only. This document makes no profitability, execution, or live-trading claim.

**Issue:** #50 — B-level XAUUSD M1 edge validation gate

**Purpose:** Record the exact thresholds, observed values, pass/fail outcomes, artifacts, hashes, seeds, and implementation events so that a future reviewer or SaaS customer can reconstruct what was tested and why a result was accepted or rejected.

---

## 1. Evidence rule

A statement such as “checked”, “green”, or “reviewed” is not scientific evidence by itself. A validation event is considered evidenced only when its numerical result, threshold, status, provenance, and artifact are recorded.

ResearchOS already applies the same principle to repository health: a locally reported checked state is unverified until the health evidence artifact exists or the corresponding CI evidence gate passes. See the repository README for this rule. 

For this XAUUSD gate, the equivalent evidence is the JSON gate artifact plus the source/walk-forward artifacts and their SHA-256 hashes.

---

## 2. Frozen B-level acceptance contract

| Gate | Required value | Observed value | Result |
|---|---:|---:|---|
| Unique OOS events | >= 10,000 | 22,500 | PASS |
| Aggregate Brier improvement | > 0 | +0.0009763019999999845 | PASS |
| 95% fold-improvement CI lower bound | > 0 | +0.0001630058955555544 | PASS |
| 95% fold-improvement CI upper bound | — | +0.0018529022222222228 | RECORDED |
| Paired permutation p-value | < 0.01 | 0.015009849901500985 | FAIL |
| Two-sided sign-test p-value | < 0.05 | 0.765991824244793 | FAIL |
| Positive fold rate | >= 70% | 24 / 45 = 53.33333333333333% | FAIL |
| Independent walk-forward audit | PASS | PASS | PASS |
| Independent source-to-result audit | PASS | PASS | PASS |
| Label-shuffle negative control | PASS | PASS | PASS |
| Temporal-leakage negative control | PASS | PASS | PASS |
| **Final B-level status** | **all gates PASS** | **NO_EDGE_OR_INCONCLUSIVE** | **FAIL / NOT AN EDGE** |

The exact gate constants are implemented in `scripts/evaluate_xauusd_m1_b_level_gate.py`: `MIN_OOS_EVENTS = 10_000`, `MIN_FOLD_IMPROVEMENT_RATE = 0.70`, `PERMUTATION_ALPHA = 0.01`, `SIGN_TEST_ALPHA = 0.05`, with 20,000 bootstrap resamples and fixed seeds. 

Important implementation detail: the current permutation evaluator uses an exact sign-flip calculation for <=20 folds and 100,000 Monte Carlo sign flips for larger fold counts. The recorded 45-fold result therefore used the Monte Carlo method with 100,000 samples.

---

## 3. Frozen walk-forward result — numerical record

**Contract**

- Asset: XAUUSD
- Timeframe: M1
- Base signal: SMA20 / SMA100 crossover
- Label: `hit_threshold_1d`
- Horizon: 1 day
- Threshold: 0.0
- Price field: close
- Direction-aware probability model

**Observed walk-forward result**

- OOS unique validation events: **22,500**
- Folds: **45**
- Aggregate model Brier: **0.2490280668**
- Aggregate baseline Brier: **0.2500043688**
- Aggregate Brier improvement: **+0.0009763019999999845**
- Positive folds: **24**
- Negative folds: **21**
- Positive fold rate: **53.33333333333333%**
- 95% fold-improvement CI: **[0.0001630058955555544, 0.0018529022222222228]**
- Paired permutation p-value: **0.015009849901500985**
- Two-sided sign-test p-value: **0.765991824244793**
- Label-shuffle negative control: **PASS / true**
- Temporal-leakage negative control: **PASS / true**

**Conclusion:** The aggregate Brier improvement is positive and its bootstrap CI is above zero, but the preregistered significance and consistency gates fail. This is **not a B-level edge**.

---

## 4. Provenance and artifact identity

### Source event artifact

`artifacts/xauusd_m1_real_events_outcomes.json`

Recorded source SHA-256:

`8a2ba847da994dc0f570b7d63bdae3ff7d976d87260ff0f533a83b26079843e4`

The underlying earlier raw dataset SHA-256 was recorded as:

`632950ee767eb8968a00331e6f8da35d3bc73e937bcb3ceb5c1b15f596939da9`

### Walk-forward artifact

`artifacts/xauusd_m1_walkforward.json`

Recorded walk-forward SHA-256:

`0b97d63f7963d1c26bb12e16d6fb66b73b901ebf4bc82adf6d628bb311d8d41c`

### Gate implementation

`scripts/evaluate_xauusd_m1_b_level_gate.py`

The implementation independently audits the walk-forward artifact, independently audits source-to-result mapping, verifies source SHA-256, recomputes fold improvements, computes CI/p-values, and executes both negative controls before producing the gate report.

---

## 5. Verification events — chronological record

### Event V01 — B-level gate mechanism implemented

The B-level gate was implemented with explicit numerical acceptance criteria. The gate cannot return `B_LEVEL_PASS` unless every required boolean gate is true.

**Evidence:** `scripts/evaluate_xauusd_m1_b_level_gate.py`.

### Event V02 — Direct-execution defect discovered

The gate script initially failed under direct execution because `scripts` was not importable in that invocation context. This was a code-execution defect, not a scientific result.

**Failure:** `ModuleNotFoundError: No module named 'scripts'`.

### Event V03 — Direct-execution defect repaired

A repository-root fallback was added to the gate script, and a regression test was added that executes the script with `--help` and verifies the expected CLI argument is present.

**Outcome:** CI was reported green for the repair, and the merge commit was `612d502828c84812da82e6c5d8846d92e23d5d1f`.

### Event V04 — Fresh real-data B-level gate execution

The corrected gate was executed against the real XAUUSD M1 walk-forward and source artifacts.

**Outcome:** exit code **2**, status **`NO_EDGE_OR_INCONCLUSIVE`**.

This was the scientifically important result. CI being green did not override it.

### Event V05 — Statistical gate failures recorded

Three acceptance gates failed:

1. Paired permutation p-value: **0.015009849901500985**, required **< 0.01**.
2. Two-sided sign-test p-value: **0.765991824244793**, required **< 0.05**.
3. Positive fold rate: **53.33333333333333%**, required **>= 70%**.

The other required gates passed, but final status remained **`NO_EDGE_OR_INCONCLUSIVE`**.

### Event V06 — Nested discovery rerun failed

Command configuration:

- train size: 2,000
- validation size: 500
- step size: 500
- minimum events: 100
- permutations: 20,000

Failure:

`RuntimeError: selected candidate failed outer minimum`

Exit code: **1**.

**Interpretation:** This was classified as a discovery-engine contract/implementation failure, not as evidence for or against an edge. The failure occurred because the selected inner candidate could have insufficient support in untouched outer OOS data, and the implementation hard-failed instead of recording that condition.

### Event V07 — Nested discovery contract repaired

PR #61 was opened to change the outer-support behavior.

New rule:

- candidate selection remains inner-only;
- outer labels are never used for candidate selection;
- insufficient outer support is recorded as `outer_support_met=false`;
- unsupported folds are excluded from aggregate discovery diagnostics;
- discovery remains `NO_EDGE_OR_INCONCLUSIVE`;
- the condition is covered by regression tests.

PR: #61 — `fix: make nested XAUUSD discovery robust to outer support failures`.

Head SHA at opening: `a6240935f7dec27df02502a432e62580b0e97d1d`.

CI run observed for that head: **run #758**, initially **queued** at the time of this record.

**Important:** queued CI is not a success result. No green claim is made here.

---

## 6. Failure register

| ID | Failure | Technical meaning | Scientific meaning | Resolution |
|---|---|---|---|---|
| F01 | `ModuleNotFoundError: No module named 'scripts'` | Direct CLI import path defect | None | Repaired with repository-root fallback + regression test |
| F02 | B-level exit code 2 | Gate criteria not all satisfied | **No validated B-level edge** | Correct rejection; no bypass |
| F03 | Permutation p = 0.015009849901500985 | Above required 0.01 | Significance gate failed | Retained as failure |
| F04 | Sign-test p = 0.765991824244793 | Above required 0.05 | Cross-fold consistency gate failed | Retained as failure |
| F05 | Positive fold rate = 53.33333333333333% | Below required 70% | Cross-fold consistency gate failed | Retained as failure |
| F06 | Nested discovery `selected candidate failed outer minimum` | Discovery implementation hard-failed on OOS support | Not an edge result | PR #61 changes this to explicit recorded support status |

---

## 7. Success register

| ID | Successful verification | Recorded value |
|---|---|---|
| S01 | Real XAUUSD M1 source resolved | Source artifact SHA recorded |
| S02 | Walk-forward OOS sample size | **22,500** |
| S03 | Walk-forward folds | **45** |
| S04 | Aggregate model Brier | **0.2490280668** |
| S05 | Aggregate baseline Brier | **0.2500043688** |
| S06 | Aggregate improvement | **+0.0009763019999999845** |
| S07 | 95% CI | **[0.0001630058955555544, 0.0018529022222222228]** |
| S08 | Independent walk-forward audit | **PASS** |
| S09 | Independent source-to-result audit | **PASS** |
| S10 | Label-shuffle negative control | **PASS** |
| S11 | Temporal-leakage negative control | **PASS** |
| S12 | Direct gate CLI regression | **PASS / CI green after repair** |

These successes do **not** imply that the B-level edge gate passed. A successful audit component and a successful scientific hypothesis test are different states.

---

## 8. Required evidence for a future B_LEVEL_PASS

A future result may be labeled `B_LEVEL_PASS` only if the recorded artifact contains all of the following simultaneously:

- independent walk-forward audit = PASS;
- independent source-to-result audit = PASS;
- unique OOS events >= **10,000**;
- aggregate Brier improvement > **0**;
- 95% CI lower bound > **0**;
- paired permutation p < **0.01**;
- two-sided sign-test p < **0.05**;
- positive fold rate >= **70%**;
- label-shuffle negative control = PASS;
- temporal-leakage negative control = PASS.

The numerical values must be present in the artifact. A prose statement such as “checked” is insufficient.

---

## 9. SaaS evidence-contract requirement

This document establishes the model for future productization:

**Every material research operation must produce machine-readable evidence and human-readable documentation.**

At minimum each operation must record:

1. operation ID;
2. UTC timestamp;
3. Git commit SHA;
4. input artifact path(s);
5. input SHA-256 hash(es);
6. frozen contract/version;
7. configuration and thresholds;
8. observed numerical results;
9. pass/fail status for each criterion;
10. aggregate final status;
11. failure reason(s), if any;
12. deterministic seeds where randomness exists;
13. output artifact path and SHA-256;
14. explicit scientific boundary and non-claims;
15. CI run/commit provenance when CI is involved.

This is the evidence trail that should later become the SaaS audit/provenance layer. It is not a substitute for the underlying raw data or statistical artifacts.

---

## 10. Current authoritative conclusion

**As of this record, ResearchOS has NOT demonstrated a B-level XAUUSD M1 edge under Issue #50's frozen acceptance contract.**

The observed data show a small positive aggregate Brier improvement (**+0.0009763019999999845**) with a 95% CI above zero, but the paired permutation test (**0.015009849901500985**), sign test (**0.765991824244793**), and positive-fold rate (**53.33333333333333%**) all fail their preregistered acceptance thresholds.

Therefore the correct scientific state is:

`NO_EDGE_OR_INCONCLUSIVE`

Any future change to the contract, thresholds, candidate-selection rules, or statistical procedure must create a new versioned evidence record rather than silently rewriting this history.
