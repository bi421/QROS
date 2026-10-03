# XAUUSD M1 research data

This directory is intentionally kept free of tracked market-data files.

## Download policy

The XAUUSD M1 dataset is an external research input and must not be committed to Git.

Preferred sources:

1. **DVC** — pull the versioned dataset from the configured DVC remote.
2. **Supabase Storage** — download the tenant/project-approved immutable artifact from the configured object-storage boundary.

Place the downloaded artifact under this directory only for local research execution. Do not commit CSV, ZIP, Parquet, or generated dataset files.

The canonical production data contract is content-addressed and evidence-backed; absence of local data must fail closed rather than silently generating or repairing observations.
