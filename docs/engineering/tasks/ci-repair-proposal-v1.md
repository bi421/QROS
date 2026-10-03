# Task Contract: Bounded CI Repair Proposal v1

## Task

- ID: engineering-ci-repair-proposal-v1
- Goal: Add a deterministic proposal-only boundary after CI failure classification.
- Why: Prevent a future repair controller from jumping directly from raw CI evidence to source mutation.
- Maximum repair attempts: 1

## Scope

### Allowed

- scripts/propose_ci_repair.py
- researchos/saas/tests/test_ci_repair_proposal.py
- docs/engineering/CI_REPAIR_PROPOSAL.md
- docs/engineering/tasks/ci-repair-proposal-v1.md

### Forbidden

- source mutation automation
- merge or deployment automation
- production migrations
- authentication and authorization
- tenant isolation
- destructive data operations
- changes to existing CI workflow semantics

## Acceptance criteria

- [ ] Only explicitly repairable classifier categories can produce a proposal.
- [ ] Missing or malformed evidence fails closed.
- [ ] Zero attempt limit fails closed.
- [ ] Non-repairable and unknown categories fail closed.
- [ ] The tool never edits files, executes repair commands, merges, or deploys.

## Validation

- Unit tests cover repairable, non-repairable, unknown, malformed, and zero-limit cases.
- Ruff and repository pre-commit gates must pass.
- GitHub CI is authoritative.

## Autonomy limits

### Allowed

- Parse classifier output.
- Emit a deterministic proposal.
- Stop on unsafe or insufficient evidence.

### Forbidden

- Modify source code.
- Execute repair commands.
- Merge pull requests.
- Deploy production changes.
- Override human approval boundaries.
