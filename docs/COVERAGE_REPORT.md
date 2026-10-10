> **Historical report — not current-main evidence.** This report was measured on 2026-08-16 and must not be cited as the coverage of a later commit. For current evidence, use the `Full Configured Test Suite + Coverage` CI artifact named `qros-coverage-<exact SHA>`; that run also enforces the configured minimum coverage floor.

# PHASE 3.2 — Coverage Measurement Report

**Date Executed:** 2026-08-16  
**Timestamp:** From direct pytest-cov execution (with HTML report generated)  
**Overall Coverage:** **77%** (CODEBASE AVERAGE)

---

## Executive Summary

Coverage analysis across `researchos/` package reveals **3157 tests executed** with:

| Metric | Value |
|--------|-------|
| **Total Lines** | 34,437 |
| **Covered Lines** | 26,686 |
| **Uncovered Lines** | 7,751 |
| **Overall Coverage %** | 77% |
| **Execution Time** | 273.59 seconds (4 min 33 sec) |

---

## Critical Finding: Modules Below 70% Coverage ⚠️

The following modules are **FLAGGED FOR PHASE 4 WORK**:

### High-Risk Modules (0-30% coverage)

| Module | Coverage | Lines | Missing | Status |
|--------|----------|-------|---------|--------|
| `quant_engine/compatibility.py` | **0%** | 1047 | 1047 | ⛔ CRITICAL — Entirely uncovered |
| `quant_engine/dataset_contracts.py` | **0%** | 70 | 70 | ⛔ CRITICAL — No test coverage |
| `machine_learning/builder.py` | **0%** | 8 | 8 | ⛔ Not tested |
| `machine_learning/contracts.py` | **0%** | 10 | 10 | ⛔ Not tested |
| `quant_engine/models.py` | **0%** | 500 | 500 | ⛔ CRITICAL — Monolithic file, legacy |
| `quant_engine/probability/mle.py` | **14%** | 64 | 55 | ⚠️ Severely untested |
| `quant_engine/fundamental/analytics.py` | **25%** | 221 | 165 | ⚠️ Severely undertested |
| `quant_engine/cpp_backend.py` | **29%** | 206 | 146 | ⚠️ C++ binding fallback; limited Python coverage |
| `quant_engine/technical/indicators.py` | **30%** | 516 | 362 | ⚠️ Technical indicators partially tested |
| `quant_engine/probability/bayesian.py` | **28%** | 107 | 77 | ⚠️ Bayesian inference undertested |
| `quant_engine/portfolio/analytics.py` | **40%** | 384 | 231 | ⚠️ Portfolio metrics incomplete coverage |
| `quant_engine/statistics.py` | **41%** | 276 | 162 | ⚠️ Statistical functions undertested |

### Medium-Risk Modules (30-70% coverage)

| Module | Coverage | Lines | Notes |
|--------|----------|-------|-------|
| `quant_engine/replay.py` | 70% | 82 | Exactly at threshold; needs expansion |
| `quant_engine/research_cpp_backend.py` | 61% | 94 | C++ integration underutilized in tests |
| `quant_engine/research_engine.py` | 60% | 162 | Engine logic needs more coverage |
| `quant_engine/econometrics/core.py` | 71% | 504 | Core econometrics moderately covered |
| `quant_engine/historical/analytics.py` | 82% | 292 | Good coverage; minor gaps remain |
| `quant_engine/technical/validation.py` | 73% | 41 | Validation logic should be more robust |
| `decision_engine/classification.py` | 73% | 274 | NEW MODULE — good baseline but phase 4 audit needed |
| `decision_engine/policy.py` | 68% | 153 | NEW MODULE — just below threshold; needs attention |
| `validation/rules.py` | 46% | 65 | Validation rules undertested |
| `validation/validators.py` | 35% | 127 | Validator implementation significantly undertested |
| `orchestration/contracts.py` | 92% | 127 | High coverage; minimal gaps |
| `pipeline/pipeline.py` | 89% | 204 | Good coverage; few gaps remain |
| `pipeline_repository/contracts.py` | 85% | 55 | Well-tested contracts |

### Strong Coverage (>90%)

The following modules have excellent test coverage and serve as **REFERENCE IMPLEMENTATIONS**:

- `objects/macro.py` — **100%** (562 lines)
- `objects/market_memory.py` — **100%** (287 lines)
- `core/identity.py` — **100%** (113 lines)
- `evidence/` package (all modules 95%+) — Evidence emission layer fully tested
- `decision_engine/action_generator.py` — **100%** (89 lines)
- `reasoning_engine/` package — 96%+ coverage
- All frozen core contracts (decision, experiment, result, etc.) — 95%+ coverage

---

## Newer Modules Status (Phase 3 Audit)

As noted in requirements, three newer modules were specifically audited:

### 1. **decision_engine/** (NEW)

| Module | Coverage | Status |
|--------|----------|--------|
| `__init__.py` | 100% | ✅ Pass |
| `action_generator.py` | 100% | ✅ Pass |
| `classification.py` | 73% | ⚠️ Needs Phase 4 expansion |
| `engine.py` | 94% | ✅ Good |
| `policy.py` | 68% | ⚠️ Below threshold; Phase 4 priority |

**Summary:** Decision engine is 87% average — good for new code but `policy.py` needs work.

### 2. **orchestration/** (NEW)

| Module | Coverage | Status |
|--------|----------|--------|
| `__init__.py` | 100% | ✅ Pass |
| `contracts.py` | 92% | ✅ Strong |
| `engine.py` | 97% | ✅ Excellent |

**Summary:** Orchestration layer is 96% average — **EXCELLENT** for new code.

### 3. **market_memory/** (NEW)

| Module | Coverage | Status |
|--------|----------|--------|
| `__init__.py` | 100% | ✅ Pass |
| `core.py` | 89% | ✅ Strong |
| `memory.py` | 96% | ✅ Excellent |
| `objects.py` | 100% | ✅ Pass |

**Summary:** Market memory is 96% average — **EXCELLENT** for new code.

---

## Phase 4 Remediation Roadmap

### Tier 1: Critical (0-30% coverage) — Must Fix

**Priority Order:**

1. **`quant_engine/compatibility.py` (0%, 1047 lines)**
   - Action: Either remove dead code or add comprehensive unit tests
   - Effort: HIGH
   - Timeline: Week 1

2. **`quant_engine/models.py` (0%, 500 lines)**
   - Action: Break into smaller modules; add test suite for each
   - Effort: HIGH
   - Timeline: Week 1-2

3. **`quant_engine/dataset_contracts.py` (0%, 70 lines)**
   - Action: Add contract validation tests
   - Effort: LOW
   - Timeline: 1-2 hours

4. **`machine_learning/{builder,contracts}.py` (0%, 18 lines total)**
   - Action: Add unit tests for ML pipeline initialization
   - Effort: LOW
   - Timeline: 1-2 hours

### Tier 2: High-Risk (30-70% coverage) — Should Fix

**Priority Order:**

1. **`validation/{rules,validators}.py` (35-46%, 192 lines)**
   - Current: Undertested validation logic
   - Action: Expand test cases for edge cases, invalid inputs
   - Effort: MEDIUM
   - Timeline: 2-3 hours

2. **`decision_engine/policy.py` (68%, 153 lines)**
   - Current: Just below threshold
   - Action: Add edge case tests, error handling tests
   - Effort: LOW-MEDIUM
   - Timeline: 2 hours

3. **`decision_engine/classification.py` (73%, 274 lines)**
   - Current: Audit for decision logic gaps
   - Action: Test more regime transitions, edge cases
   - Effort: MEDIUM
   - Timeline: 2-3 hours

4. **`quant_engine/technical/validation.py` (73%, 41 lines)**
   - Current: Validation logic undertested
   - Action: Add comprehensive validation tests
   - Effort: LOW
   - Timeline: 1-2 hours

### Tier 3: Enhancement (70-90% coverage) — Nice to Have

**Modules with minor gaps:**

- `quant_engine/historical/analytics.py` (82%) — add edge case tests
- `pipeline/pipeline.py` (89%) — test error paths
- `orchestration/contracts.py` (92%) — test boundary cases

---

## Test Isolation Status (Phase 3.3 Preview)

**Coverage report does not indicate database isolation issues at coverage level.** Phase 3.3 detailed audit will verify:

- [ ] Direct `researchos.db` references in tests
- [ ] Temporary path fixtures usage
- [ ] Database mock/fixture injection

---

## Coverage Report Location

Full HTML coverage report generated to:  
**`htmlcov/index.html`** — Open in browser for interactive navigation

---

## Sign-Off

✅ **COVERAGE MEASUREMENT COMPLETE**  
- Overall: 77% (acceptable for production code)
- 0% modules: 5 files (mostly legacy/compatibility)
- Phase 4 work prioritized by tier
- Newer modules (decision_engine, orchestration, market_memory) track well (87-96% average)

All critical and high-risk modules flagged with Phase 4 remediation roadmap.

---
