# CI Failure Classifier v1

The CI failure classifier is a deterministic, read-only boundary between observed GitHub Actions failures and any future repair agent.

## Contract

Input is raw observed CI log text. Output is JSON with:

- `category`
- `confidence`
- `repairable`
- `evidence`

Supported categories are the categories defined by the Engineering Agent Contract:

- implementation defect
- test/contract mismatch
- formatting/static failure
- environment/tooling failure
- CI orchestration failure
- missing prerequisite
- ambiguous/unsafe

## Safety rules

The classifier:

1. never edits repository files;
2. never chooses a code change;
3. never treats an empty log as repairable;
4. treats orchestration anomalies such as a failed run with no jobs as non-repairable;
5. returns `ambiguous/unsafe` when multiple independent failure classes conflict;
6. includes matched signatures so a later repair step can audit the reason.

A future repair controller must treat `repairable=false` as a hard stop.

## Deliberate limitation

This v1 is signature-based rather than an LLM judgment system. It is intentionally conservative. A real CI failure can contain several layers of symptoms; conflicting signals therefore fail closed instead of guessing.

## CLI

Read a log file:

```text
python scripts/classify_ci_failure.py path/to/ci.log
```

Or pipe a log:

```text
cat ci.log | python scripts/classify_ci_failure.py
```

The output is deterministic JSON suitable for downstream automation.

## Next boundary

This classifier does not implement automatic repair. The next engineering slice may add a bounded repair policy that accepts only explicitly repairable categories, enforces the task contract, records each attempt, and stops at the configured attempt limit.
