# ResearchOS Analysis Execution Contract 2026

**Status:** Mandatory design contract 1.0  
**Date:** 2026-09-17

The purpose of this contract is to make every quantitative method operationally explicit: **when it runs, what it consumes, what it emits, and what may consume the result next**.

## 1. Universal AnalysisResult

Every governed quantitative method emits an AnalysisResult containing, at minimum:

```text
analysis_id
claim_id
analysis_class
population_definition
time_window
data_version
data_hash
feature_version
label_version
method
model_version
assumptions
sample_size
effective_sample_size
point_estimate
uncertainty_interval
probability_definition
effect_size
diagnostics
warnings
multiple_testing_context
selection_count
integrity_gate_status
out_of_sample_status
replication_status
calibration_status
economic_cost_model
result_artifact_hash
```

## 2. Method trigger matrix

| Method | Trigger | Primary input | Main output | Downstream |
|---|---|---|---|---|
| Expected Value | binary/continuous payoff hypothesis | outcome distribution | EV + cost-adjusted EV | payoff/risk/economic validation |
| Conditional Probability | condition/regime defined | events + condition | P(A\|B) | Bayes/regime analysis |
| Bayes | prior + evidence model declared | prior + likelihood/evidence | posterior | claim evidence state |
| Binomial/Beta-Binomial | binary outcome | wins/losses | probability + interval | uncertainty/decision analysis |
| Bootstrap | IID assumption defensible | metric sample | sampling distribution | CI/inference |
| Block Bootstrap | serial dependence present | time-ordered sample | dependence-aware distribution | inference/risk |
| Kelly | validated win/payoff inputs | p, q, payoff odds | mathematical sizing fraction | risk sensitivity |
| VaR | loss distribution + horizon | returns/losses | quantile loss | risk/tail |
| Expected Shortfall | VaR/tail definition | loss distribution | average tail loss | risk/tail |
| GARCH | volatility clustering/model hypothesis | return series | volatility dynamics/forecast | VaR/ES/stress |
| GBM | diffusion baseline hypothesis | price/return series | drift/volatility + diagnostics | simulation/baseline comparison |
| OU | mean-reversion hypothesis | stationary/deviation series | mean, speed, vol, half-life | mean-reversion evidence |
| Student-t | heavy-tail diagnostic/model need | returns/residuals | df + fit diagnostics | VaR/ES/GARCH |
| EVT | extreme-tail hypothesis/need | losses + threshold | tail model/quantiles | extreme risk |
| Copula | joint dependence hypothesis | marginals + dependence data | joint/tail dependence | stress scenarios |
| Shannon Entropy | uncertainty/information analysis | discrete states | entropy | information analysis |
| Mutual Information | feature-target information test | paired variables | MI + null/permutation context | feature research |
| Sharpe inference | return series + benchmark | returns | Sharpe + uncertainty | PSR/DSR/OOS |
| PSR | Sharpe threshold comparison | Sharpe sample + threshold | probability Sharpe exceeds threshold | selection/OOS |
| DSR | multiple strategy/model selection | Sharpe + trial history | selection-adjusted inference | claim validation |
| PBO | model/strategy selection history | candidate results | overfitting probability measure | selection gate |
| CPCV | path-dependent OOS validation | labeled time series | distribution of OOS paths | robustness/replication |
| Reality Check | multiple candidate search | candidate performance | selection-aware test | claim validation |
| SPA | candidate search with benchmark | candidate performance | selection-aware test | claim validation |
| Calibration | probabilistic prediction exists | predictions + outcomes | Brier/log loss/calibration diagnostics | probability quality |

## 3. Execution state machine

```text
NOT_ELIGIBLE
    ↓
ELIGIBLE
    ↓
RUNNING
    ↓
COMPLETED
    ↓
VALIDATED
    ↓
CONSUMABLE
```

Failure branches:

```text
RUNNING → FAILED
COMPLETED → INVALID
VALIDATED → CONTRADICTED
CONSUMABLE → SUPERSEDED
```

A failed or invalid analysis does not silently disappear.

## 4. Example — 60-minute XAUUSD edge

```text
Claim
  ↓
Plan Lock
  ↓
Data Integrity Gate
  ↓
Event extraction
  ↓
Expected Value
  ↓
Win probability + interval
  ↓
Block Bootstrap
  ↓
VaR / ES
  ↓
Conditional Probability by macro regime
  ↓
Sharpe / PSR
  ↓
DSR + search history
  ↓
CPCV / purged OOS
  ↓
Cost/slippage model
  ↓
Replication
  ↓
Claim status
```

## 5. Method selection rules

The orchestrator must prefer the **minimum sufficient analysis set** rather than running every model on every claim.

For example:

- a mean-reversion claim should trigger stationarity/autocorrelation/OU diagnostics;
- a tail-risk claim should trigger EVT/ES and distribution diagnostics;
- a feature-information claim should trigger MI plus a suitable null/permutation test;
- a strategy-selection claim should trigger search accounting and selection-aware inference;
- a probabilistic classifier should trigger calibration diagnostics;
- a volatility claim should trigger volatility clustering/model diagnostics.

The orchestrator may add mandatory safety analyses, but must not invent post-hoc analyses solely to improve a result.

## 6. Post-hoc analysis rule

Any analysis added after seeing a material result must be marked `POST_HOC`. Post-hoc results may be exploratory evidence, but cannot be represented as pre-registered confirmation.

## 7. Promotion rule

No AnalysisResult directly creates Knowledge. The canonical promotion path remains:

`AnalysisResult → Validation → Finding → Replication/Contradiction → Knowledge Status`

## 8. Human-readable result

Every analysis must be explainable in plain language:

- what was tested;
- why it ran;
- what data it used;
- what it found;
- how uncertain the result is;
- what assumptions matter;
- what could invalidate it;
- what should happen next.

The UI may simplify presentation, but it must not remove provenance or material uncertainty.
