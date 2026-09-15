# XAUUSD M1 nested discovery: outer support handling

The nested discovery stage selects candidates using only the chronological inner training/validation split. Outer OOS labels are never used for candidate selection.

A selected candidate may have fewer than `min_events` observations in an outer validation fold. This is an outer-support condition, not a reason to terminate discovery. The fold is recorded with `outer_support_met=false` and excluded from aggregate Brier/sign/permutation diagnostics. This keeps the discovery run auditable without silently treating weak-support OOS observations as confirmation evidence.

Any candidate that survives discovery still requires a separate confirmation gate on untouched data. Discovery status remains `NO_EDGE_OR_INCONCLUSIVE`.
