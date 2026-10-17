# QROS Research Controls V1

This additive module implements research-only controls without replacing existing QROS engines or authorizing broker orders.

- `calculate_quarter_kelly_size`: cost-adjusted binary Kelly fraction, quarter-Kelly scaling, strict maximum risk fraction (at most 2%), stop-distance/contract-multiplier sizing, and fail-closed handling.
- `apply_bnf_mean_reversion`: Polars rolling mean, relative deviation thresholds (`-0.35`, `-0.20`), full-window requirement, optional ascending unique timestamp validation, and a turnover capacity gate for `BUY_STRONG` only.
- `screen_insider_clusters`: reuse `researchos.orchestration.alternative_data_research`; only verified public, open-market purchases with reviewed-clear batch status qualify. This source is not fetched by the module.
- `unified_research_gate`: all statistical/data/risk/BNF gates must pass. Insider cluster is recorded as evidence only and never overrides a failed gate.
- `build_audit_record`: deterministic SHA-256 hashes for canonical input and decision JSON, with source commit and config version.
- `qros_research_controls`: isolated C++20/Nanobind kernel for Kelly sizing and BNF signals. Parity tests compare it to Python results.

The Kelly payoff inputs `average_win`, `average_loss`, and `cost_per_unit` are account-currency values per one unit. `contract_multiplier` converts the entry-to-stop price distance into account-currency risk per unit. Broker-specific lot steps, margin, contract definitions, spread and slippage must be supplied/validated by the caller before any production use. A candidate result is never an order instruction.

The robustness score passed to the unified gate must be a higher-is-better robustness metric in `[0, 1]`, not a higher-is-worse overfitting risk score.
