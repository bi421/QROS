# ResearchOS 2026 Probability & Trading-Edge Framework

**Status:** Proposed quantitative research standard 0.1  
**Date:** 2026-09-17  
**Scope:** Probability, statistics, stochastic processes, financial econometrics and information-theoretic evidence used to evaluate trading research claims.

## 1. Purpose

ResearchOS must not reduce a trading claim to win rate. A trading edge is a statistical and economic property that must survive uncertainty, dependence, non-stationarity, costs, multiple testing and independent validation.

The Probability & Edge Framework therefore separates five questions:

1. **What is the event probability?**
2. **What is the conditional return/risk distribution?**
3. **How uncertain is the estimate?**
4. **How much of the apparent edge could be selection, dependence or overfitting?**
5. **Does the evidence remain economically meaningful after costs and out-of-sample validation?**

The framework is a measurement system, not a promise that any formula predicts markets.

## 2. Evidence hierarchy

```text
OBSERVATIONS
    ↓
EVENT / RETURN DISTRIBUTION
    ↓
CONDITIONAL PROBABILITY
    ↓
EXPECTED PAYOFF + RISK
    ↓
SAMPLING / ESTIMATION UNCERTAINTY
    ↓
DEPENDENCE + TIME-SERIES EFFECTS
    ↓
MULTIPLE TESTING / SELECTION BIAS
    ↓
OUT-OF-SAMPLE + ROBUSTNESS + REPLICATION
    ↓
ECONOMIC EDGE ASSESSMENT
```

No downstream statistic can repair a failed upstream integrity condition.

---

## 3. Probability & statistics

### 3.1 Expected value

For a discrete outcome system:

\[
E[X] = \sum_i p_i x_i
\]

For a simplified win/loss strategy:

\[
EV = p_w \bar{W} - (1-p_w)|\bar{L}|
\]

where:

- \(p_w\) = probability of a winning trade;
- \(\bar W\) = mean win;
- \(\bar L\) = mean loss magnitude.

For research, the distribution of returns is preferred to a binary win/loss reduction because skew, tail losses and payoff asymmetry can materially change the conclusion.

### 3.2 Conditional probability

For a signal/event \(B\) and outcome \(A\):

\[
P(A|B) = \frac{P(B|A)P(A)}{P(B)}
\]

ResearchOS should distinguish:

- unconditional probability \(P(A)\);
- conditional probability \(P(A|B)\);
- likelihood \(P(B|A)\);
- posterior probability after observing new information.

A signal's raw hit rate is not equivalent to a causal effect or a calibrated posterior probability.

### 3.3 Bayes theorem

\[
P(H|D) = \frac{P(D|H)P(H)}{P(D)}
\]

Bayesian updating is useful when prior assumptions and likelihood models are explicitly declared. Priors must be versioned, and posterior probability must never be presented as empirical certainty when model assumptions are unverified.

### 3.4 Binomial uncertainty

For \(k\) successes in \(n\) approximately independent binary trials:

\[
\hat p = \frac{k}{n}
\]

ResearchOS should prefer exact or Wilson/Beta-based intervals over a naive normal approximation when samples are small or probabilities are near 0/1.

A Beta-Binomial model can represent posterior uncertainty:

\[
p \sim Beta(\alpha,\beta)
\]

with a declared prior rather than an implicit one.

### 3.5 Sampling uncertainty

Every estimated edge metric should expose an uncertainty interval or distribution where mathematically appropriate. Examples:

- mean return confidence interval;
- win-rate interval;
- quantile interval;
- bootstrap distribution;
- posterior interval;
- standard error.

A point estimate without its uncertainty is incomplete evidence.

### 3.6 Hypothesis testing

ResearchOS may record:

- null and alternative hypotheses;
- test statistic;
- p-value;
- confidence level;
- effect size;
- power or minimum detectable effect;
- correction for multiple comparisons where applicable.

A p-value is not the probability that a hypothesis is true. Statistical significance is not equivalent to economic significance.

### 3.7 Effect size

The system must preserve effect magnitude separately from statistical significance. Examples include:

- mean excess return;
- median excess return;
- volatility-adjusted return;
- odds ratio;
- standardized mean difference;
- expected utility change.

---

## 4. Trading payoff and position sizing

### 4.1 Kelly criterion

For a binary bet with win probability \(p\), loss probability \(q=1-p\), and net win/loss odds \(b\):

\[
f^* = \frac{bp-q}{b}
\]

This is an idealized growth-optimal fraction under restrictive assumptions. It is not a default risk limit for live trading.

ResearchOS should distinguish:

- theoretical full Kelly;
- fractional Kelly;
- externally imposed risk cap;
- uncertainty-adjusted sizing.

Estimated \(p\) and payoff odds are uncertain, so sizing must not silently treat estimates as known constants.

### 4.2 Expected log growth

For multiplicative wealth:

\[
G = E[\ln(1+fR)]
\]

where \(f\) is exposure and \(R\) is strategy return. This connects position sizing with the long-run growth objective, but it remains sensitive to distributional assumptions and drawdown tolerance.

### 4.3 Risk-adjusted performance

ResearchOS should retain, where relevant:

- Sharpe ratio;
- Sortino ratio;
- Calmar ratio;
- maximum drawdown;
- expected shortfall;
- downside deviation;
- turnover and transaction-cost drag.

These are descriptors of observed or modeled performance, not standalone proof of predictive edge.

---

## 5. Financial time series and econometrics

### 5.1 Stationarity

Before applying stationary time-series models, test and document assumptions about stationarity. Relevant tools can include:

- Augmented Dickey-Fuller;
- Phillips-Perron;
- KPSS;
- structural-break tests.

A failure to establish stationarity must not be silently repaired by differencing or detrending without recording the transformation.

### 5.2 Autocorrelation

For returns or residuals, ResearchOS should be able to inspect:

\[
\rho_k = \frac{Cov(X_t,X_{t-k})}{Var(X_t)}
\]

and, where appropriate:

- ACF/PACF;
- Ljung-Box tests;
- residual diagnostics.

### 5.3 AR/MA/ARIMA-family models

Where appropriate:

\[
X_t = c + \sum_{i=1}^{p}\phi_i X_{t-i} + \epsilon_t
\]

and related ARMA/ARIMA specifications may model conditional dynamics. Model order, transformations and selection procedure must be recorded.

### 5.4 GARCH

A GARCH(1,1) conditional variance model is:

\[
\sigma_t^2 = \omega + \alpha\epsilon_{t-1}^2 + \beta\sigma_{t-1}^2
\]

with constraints appropriate to the chosen specification. The model represents volatility clustering; it does not by itself establish directional predictability.

Extensions such as EGARCH, GJR-GARCH and Student-t innovations may be used when justified by diagnostics.

### 5.5 Volatility forecasting

ResearchOS should separate:

- realized volatility;
- conditional volatility forecast;
- implied volatility where available;
- forecast error.

Forecast quality must be evaluated out of sample rather than inferred from in-sample fit.

### 5.6 VaR and Expected Shortfall

Parametric VaR is commonly represented as a quantile of the loss distribution. Under a Gaussian location-scale model:

\[
VaR_\alpha = \mu + z_\alpha\sigma
\]

with sign convention explicitly declared because risk reporting conventions differ.

Expected Shortfall is the conditional tail loss beyond VaR:

\[
ES_\alpha = E[L \mid L \ge VaR_\alpha]
\]

for a loss variable \(L\).

ResearchOS should prefer empirically or distributionally justified tail models over blindly assuming Gaussian returns.

---

## 6. Stochastic processes and stochastic calculus

### 6.1 Geometric Brownian Motion

A GBM model is:

\[
dS_t = \mu S_tdt + \sigma S_tdW_t
\]

It is a useful mathematical benchmark and simulation model. It is not a claim that real market prices literally follow GBM.

Under GBM:

\[
d\ln S_t = (\mu-\frac12\sigma^2)dt + \sigma dW_t
\]

ResearchOS must label GBM-generated results as model-based evidence rather than observed-market evidence.

### 6.2 Ornstein-Uhlenbeck process

For mean-reverting state \(X_t\):

\[
dX_t = \theta(\mu-X_t)dt + \sigma dW_t
\]

where \(\theta\) controls mean-reversion speed and \(\mu\) is the long-run mean.

For pairs/spread research, the system should test whether the estimated process is stable across time rather than assuming mean reversion from visual appearance.

### 6.3 Diffusion and jump models

Where tail behavior requires it, research may consider:

- jump-diffusion models;
- Lévy processes;
- stochastic volatility;
- regime-switching processes.

The model class must be treated as an explicit hypothesis with parameter uncertainty and out-of-sample diagnostics.

---

## 7. Distributional robustness and fat tails

### 7.1 Why Gaussian assumptions are insufficient

Financial returns can exhibit heavy tails, volatility clustering, skewness and dependence. Therefore Gaussian assumptions must be declared rather than treated as universal truth.

### 7.2 Student-t innovations

A Student-t distribution can model heavier tails than a Gaussian distribution. Degrees of freedom \(\nu\) become a versioned model parameter and must be estimated and validated.

### 7.3 Extreme Value Theory

For tail events, ResearchOS should support EVT concepts such as:

- block maxima / Generalized Extreme Value;
- Peaks Over Threshold;
- Generalized Pareto Distribution;
- tail-index estimation;
- threshold sensitivity.

Tail estimates must report threshold choice and uncertainty.

### 7.4 Copulas and dependence

Copulas separate marginal distributions from dependence structure. ResearchOS may support:

- Gaussian copula;
- Student-t copula;
- Archimedean copulas;
- empirical/non-parametric dependence methods.

Copula choice is itself a model assumption and must be validated rather than selected because it produces a desirable backtest.

### 7.5 Tail dependence

For multi-asset or factor research, the system should distinguish ordinary correlation from tail dependence. Correlation can remain moderate while joint extreme losses become materially more likely.

---

## 8. Information theory

### 8.1 Shannon entropy

For discrete states with probabilities \(p_i\):

\[
H(X)=-\sum_i p_i\log p_i
\]

Entropy measures uncertainty of a specified state distribution. High entropy does not automatically mean “noise,” and low entropy does not automatically mean tradable signal.

### 8.2 Conditional entropy

\[
H(Y|X)=-\sum_{x,y}p(x,y)\log p(y|x)
\]

This can quantify remaining uncertainty in an outcome after conditioning on an information set.

### 8.3 Mutual information

\[
I(X;Y)=\sum_{x,y}p(x,y)\log\frac{p(x,y)}{p(x)p(y)}
\]

Mutual information can detect nonlinear dependence that correlation misses. Estimator choice, discretization and finite-sample bias must be recorded.

### 8.4 Information gain

A research feature can be evaluated by reduction in uncertainty:

\[
IG(Y;X)=H(Y)-H(Y|X)
\]

Information gain is not equivalent to economic profit. It must be connected to an explicit trading decision and validated out of sample.

---

## 9. Dependence, resampling and uncertainty

Financial observations are often serially and cross-sectionally dependent. IID bootstrap assumptions can therefore be invalid.

ResearchOS should support or record the justification for:

- IID bootstrap where defensible;
- block bootstrap;
- stationary bootstrap;
- moving-block bootstrap;
- cluster/bootstrap methods for grouped dependence;
- permutation tests that preserve the relevant null structure.

Repeated observations from the same regime, instrument, event or dataset must not be counted as independent evidence without justification.

---

## 10. Sharpe-ratio and performance inference

A Sharpe ratio estimate is itself uncertain and can be distorted by non-normality, autocorrelation, non-stationarity and selection.

ResearchOS should distinguish:

1. observed Sharpe;
2. uncertainty around Sharpe;
3. probability of exceeding a reference threshold;
4. selection-adjusted inference;
5. out-of-sample Sharpe.

Where suitable, the framework can include Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR). DSR is particularly relevant when many candidate strategies have been searched.

A high observed Sharpe after extensive search is not treated as equivalent evidence to the same Sharpe obtained from a predeclared single test.

---

## 11. Multiple testing and backtest overfitting

A serious probability engine must account for the research process itself.

Track at minimum:

```text
hypotheses tested
parameterizations tried
datasets tried
feature sets tried
model families tried
validation windows tried
selection decisions
failed experiments
discarded experiments
reused datasets
```

Relevant methods include:

- family-wise error control;
- false discovery rate control;
- White Reality Check;
- Hansen SPA;
- Probability of Backtest Overfitting (PBO);
- Combinatorial Purged Cross-Validation (CPCV);
- purging and embargo;
- Deflated Sharpe Ratio.

These methods answer different questions and should not be collapsed into one “confidence score.”

---

## 12. Calibration: probability must mean what it says

When ResearchOS reports a probability such as \(P(Y>0|X) = 0.67\), it must distinguish:

- empirical frequency estimate;
- model-implied probability;
- Bayesian posterior;
- resampling probability;
- simulation probability;
- calibrated predictive probability.

For probabilistic forecasts, evaluate calibration with appropriate tools such as:

- reliability diagrams;
- Brier score;
- log loss;
- calibration slope/intercept;
- proper scoring rules.

A probability forecast is useful only if its numerical meaning is stable under validation.

---

## 13. Regime dependence and conditional edge

A single unconditional edge can conceal regime-specific behavior.

ResearchOS should permit conditional analysis by declared variables such as:

- volatility regime;
- trend/range regime;
- liquidity regime;
- macro regime;
- session/time-of-day;
- event regime;
- cross-asset state.

The system must guard against creating arbitrary regimes after seeing results. Regime definitions are part of the research plan and search budget.

---

## 14. Economic significance

Statistical evidence must be translated into an executable economic quantity without silently adding assumptions.

At minimum record:

\[
NetReturn = GrossReturn - Costs - Slippage - Fees - Financing - OtherDeclaredDrag
\]

Also record:

- turnover;
- capacity/liquidity assumptions;
- spread model;
- market impact assumptions where applicable;
- latency assumptions;
- borrow/funding costs where relevant;
- execution constraints.

An effect that disappears under realistic costs is not accepted as an economically usable edge merely because its raw p-value is small.

---

## 15. Probability Engine output contract

Every probability-producing analysis should return a structured result containing, where applicable:

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
model_family
model_version
assumptions
prior_definition
sample_size
effective_sample_size
dependence_method
point_estimate
uncertainty_interval
probability_definition
test_definition
effect_size
risk_metrics
tail_model
multiple_testing_context
selection_count
integrity_gate_status
out_of_sample_status
replication_status
calibration_status
economic_cost_model
result_artifact_hash
```

Missing fields must be represented as explicit `UNKNOWN`/`NOT_APPLICABLE`, not silently inferred.

---

## 16. Edge assessment state machine

Probability calculations feed an evidence state machine; they do not directly promote a strategy to “edge.”

```text
UNTESTED
   ↓
ESTIMATED
   ↓
UNCERTAINTY_QUANTIFIED
   ↓
INTEGRITY_PASSED
   ↓
OUT_OF_SAMPLE_CHECKED
   ↓
ROBUSTNESS_CHECKED
   ↓
SELECTION_ADJUSTED
   ↓
REPLICATED
   ├── CONTRADICTED
   ├── INCONCLUSIVE
   └── SUPPORTED
```

`SUPPORTED` means that the declared evidence requirements were met. It does not mean guaranteed future profitability.

---

## 17. What ResearchOS must never do

ResearchOS must not:

- equate win rate with edge;
- equate p-value with probability of truth;
- equate correlation with causation;
- treat a Gaussian model as reality;
- treat one backtest as independent evidence after repeated search;
- hide failed experiments;
- silently change sample definitions;
- silently repair missing data;
- use future information in a probability estimate;
- report model-implied probability as observed frequency;
- report a point estimate without relevant uncertainty;
- promote a strategy because one metric is favorable;
- convert an LLM opinion into empirical evidence.

---

## 18. Minimum edge-validation bundle

For a quantitative trading claim, the minimum serious evidence bundle is:

```text
1. Claim + falsification condition
2. Locked research plan
3. Point-in-time data contract
4. Temporal/data integrity gates
5. Distribution + conditional probability estimate
6. Effect size + expected value
7. Uncertainty interval / resampling distribution
8. Dependence-aware inference
9. Tail-risk analysis
10. Multiple-testing / search-budget accounting
11. Out-of-sample validation
12. Robustness across reasonable assumptions
13. Economic cost model
14. Independent replication
15. Calibration where probabilities are forecast
16. Complete reproducibility manifest
17. Supporting + contradicting evidence history
```

Only after this bundle satisfies the claim's declared evidence requirements may the result be considered for `SUPPORTED` evidence state and eventual Knowledge promotion.

## 19. Implementation mapping

The framework should be implemented as deterministic domain services rather than as a single opaque “AI probability score.”

```text
Probability primitives
 ├── descriptive statistics
 ├── distribution fitting
 ├── conditional probability / Bayes
 ├── uncertainty estimation
 └── calibration

Time-series / econometrics
 ├── stationarity
 ├── autocorrelation
 ├── volatility models
 ├── GARCH family
 └── regime analysis

Stochastic models
 ├── GBM benchmark
 ├── OU / mean reversion
 ├── stochastic volatility
 └── jump / regime-switching models

Tail & dependence
 ├── Student-t
 ├── EVT
 ├── copulas
 └── tail dependence

Information theory
 ├── entropy
 ├── conditional entropy
 ├── mutual information
 └── information gain

Inference integrity
 ├── bootstrap / block bootstrap
 ├── multiple testing
 ├── PBO
 ├── CPCV / purging / embargo
 ├── PSR / DSR
 └── Reality Check / SPA

Economic validation
 ├── costs / slippage
 ├── turnover
 ├── capacity
 ├── drawdown / ES
 └── replication
```

Each service must produce versioned, reproducible artifacts that attach to the Research Claim evidence graph.

## 20. Core principle

> **A trading edge is not a number. It is a claim whose probability estimate, uncertainty, dependence structure, tail behavior, search history, economic impact and replication history are all inspectable.**
