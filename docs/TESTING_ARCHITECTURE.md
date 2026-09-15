# ResearchOS Testing Architecture

ResearchOS separates developer feedback from expensive scientific and performance evidence.

## Profiles

| Profile | Purpose | Default |
|---|---|---|
| `fast` | Changed/affected tests only; frozen evidence is skipped unless its dependency changed | Yes |
| `frozen` | Fast tests plus all registered frozen evidence groups | Explicit |
| `full` | Entire pytest suite | Explicit / CI |

Run locally:

```powershell
python scripts/preflight.py
python scripts/preflight.py --frozen
python scripts/preflight.py --full
```

Equivalent profile form:

```powershell
python scripts/preflight.py --profile fast
python scripts/preflight.py --profile frozen
python scripts/preflight.py --profile full
```

## Frozen means validated, not disabled

A frozen test remains in the repository and remains directly runnable. It is removed from the default feedback path because it is expensive and its evidence is already validated.

A frozen group is automatically invalidated when one of its declared dependency paths changes. That causes the group to run during the fast preflight. This makes the optimization dependency-aware rather than a permanent skip.

The current expensive evidence groups include:

- Phase 5.2 feature-set comparison/reproducibility
- Institutional 10k audit-chain verification performance

## What belongs where

### Fast

Use for deterministic unit tests, changed tests, and narrow package-level regression tests. These should provide feedback in seconds whenever possible.

### Frozen

Use for expensive tests whose purpose is durable scientific, reproducibility, scale, or performance evidence. They should have an explicit dependency boundary so a source change invalidates the evidence.

### Full

Use for release confidence, main/nightly validation, and compatibility/integration coverage. Full CI remains authoritative and is not replaced by local preflight.

## Tooling ownership

- Ruff is enforced by pre-commit; preflight does not duplicate it.
- UTF-8/BOM integrity is enforced by pre-commit; preflight does not duplicate it.
- Native C++ configure/build remains authoritative in CI. Local preflight only reports whether native inputs changed.
- `scripts/preflight.py` is the routing layer, not the scientific test authority.

## Why this exists

The previous full-suite measurement was about 199 seconds. The five slowest tests consumed about 147 seconds, roughly 74% of the run. Re-running those tests for unrelated edits creates feedback latency without adding new evidence.

The architecture therefore optimizes for **evidence reuse**: unchanged validated dependencies keep their expensive tests frozen; changed dependencies invalidate the relevant evidence automatically.
