# Canonical Engine Ownership

Status: enforced by repository layout.

## Data

researchos.data_engine is the canonical Python data-engine API.

researchos.engines.data was an older duplicate implementation. Consumers are
being migrated to researchos.data_engine; the duplicate package must not
receive new features.

The canonical data engine owns:
- market-data contracts and records
- CSV loading and dataset construction
- validation and integrity hashing
- repositories and queries
- data-source adapters

## Quant

researchos.quant_engine is the canonical Python research/quant API.

researchos.engines.quant is the C++/nanobind computation backend and is not a
second Python quant API. Python research code must import the public quant
contracts from researchos.quant_engine and reach C++ only through an explicit
backend adapter.

This distinction is intentional:
- researchos.quant_engine = domain/research contract
- researchos.engines.quant = native implementation backend

No new duplicate execution.py, indicators.py, or strategy.py API should be
added under the native engine tree.

## Enforcement

CI and architecture tests should reject:
1. imports of researchos.engines.data;
2. new Python API modules that duplicate researchos.quant_engine under the
   native engine tree;
3. root-level executable Python scripts.

Historical documentation may remain under docs/archive; deleting it from Git
history would require history rewriting and is not part of ordinary cleanup.
