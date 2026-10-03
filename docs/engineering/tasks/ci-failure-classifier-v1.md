# Task Contract: CI Failure Classifier v1

## Task

- ID: engineering-ci-failure-classifier-v1
- Goal: Add a deterministic, fail-closed classifier for observed CI failure logs.
- Why: Give the QROS repair loop a bounded classification step before any source change.
- Current branch/ref: feat/qros-agent-ci-failure-classifier-v1
- Maximum repair attempts: 0

## Scope

### Allowed
- scripts/classify_ci_failure.py
- researchos/saas/tests/test_ci_failure_classifier.py
- docs/engineering/CI_FAILURE_CLASSIFIER.md
- docs/engineering/tasks/ci-failure-classifier-v1.md

### Forbidden
- production migrations
- authentication and authorization
- tenant isolation
- deployment or merge automation
- existing CI workflow semantics
- destructive data operations

## Preconditions

- The existing Agent Contract v1 remains active.
- The classifier receives observed log text only.
- Classification must not mutate repository state.

## Acceptance criteria

- [ ] Classify supported failure signatures deterministically.
- [ ] Return an explicit ambiguous result when evidence is insufficient or conflicting.
- [ ] Never classify an empty log as repairable.
- [ ] Never classify CI orchestration anomalies as implementation defects.
- [ ] Include matched evidence in machine-readable output.

## Validation

- Unit tests cover every supported category and ambiguous cases.
- Ruff and repository pre-commit gates must pass.
- GitHub CI is authoritative for compatibility and integration.

## Risk

- Misclassification could cause an unsafe repair decision.
- Therefore the classifier is advisory and must fail closed on uncertainty.

## Autonomy limits

### Allowed
- Parse logs.
- Emit a deterministic classification.
- Support downstream bounded repair decisions.

### Forbidden
- Modify source code automatically.
- Merge pull requests.
- Deploy production changes.
- Override human approval boundaries.

## Completion evidence

- Commit SHA.
- Local validation output.
- GitHub CI run evidence.
- Test results for deterministic and fail-closed behavior.
