# Task Contract: qros-agent v1

## Task

- ID: engineering-qros-agent-v1
- Goal: Add a deterministic QROS engineering-agent control plane that validates a task contract, classifies observed CI failure evidence, and produces a bounded repair proposal without mutating source.
- Why: Establish the safe execution kernel before any future model-backed repair executor is allowed to change QROS.

## Scope

### Allowed
- scripts/qros_agent.py
- researchos/saas/tests/test_qros_agent.py
- docs/engineering/QROS_AGENT_V1.md
- docs/engineering/tasks/qros-agent-v1.md

### Forbidden
- production migrations
- authentication and authorization
- tenant isolation
- deployment or merge automation
- existing CI workflow semantics
- source mutation automation
- destructive data operations
- changes to the scientific core

## Preconditions

- Current branch/ref: feat/qros-agent-v1
- Required existing contracts: docs/engineering/AGENT_CONTRACT.md, docs/engineering/TASK_CONTRACT.md
- Required existing boundaries: scripts/validate_task_contract.py, scripts/classify_ci_failure.py, scripts/propose_ci_repair.py

## Acceptance criteria

- [ ] A valid task contract is required before an agent decision is emitted.
- [ ] CI evidence is classified only by the existing deterministic classifier.
- [ ] Repair authority is bounded by the configured attempt limit.
- [ ] Non-repairable, malformed, empty, or ambiguous evidence fails closed.
- [x] The controller requires explicit approval provenance before any governed repair command can execute.
- [x] Governed execution is restricted to the command allowlist and explicit allowed paths.
- [x] Approval binds approver identity, approval timestamp, proposal identity, governed action, scope, and attempt authority.
- [x] Attempt authority is held by a process-local persistent ledger and cannot be reset by replaying the same executor call.
- [x] Every executed or failed governed attempt emits an immutable receipt containing contract, proposal, command, approval, pre-execution SHA, diff, stdout, stderr, return code, attempt number, and next boundary.
- [x] Execution stops when the repository worktree is not clean before execution or its base SHA cannot be established.
- [ ] The controller never merges or deploys.
- [ ] Machine-readable output records task validation, classification, proposal, and stop/continue state.

## Validation

- [ ] targeted tests: python -m pytest researchos/saas/tests/test_qros_agent.py -q
- [ ] python scripts/qros_agent.py --help
- [ ] python scripts/qros_agent.py <contract> <log> --attempt-limit 1
- [ ] ruff check scripts/qros_agent.py researchos/saas/tests/test_qros_agent.py
- [ ] git diff --check
- [ ] governed executor boundary tests

## Risk

- Security impact: control-plane only; no credentials or privileged operations.
- Tenant-isolation impact: none.
- Data-integrity impact: read-only/proposal-only.
- Migration impact: none.
- API compatibility impact: none.

## Autonomy limits

- Maximum repair attempts: configured explicitly at proposal time; execution additionally requires one persistent AttemptLedger for the governed chain.
- Stop conditions: invalid task contract, ambiguous/unsafe classification, non-repairable classification, malformed evidence, zero attempt limit.
- Human approval required for: source mutation, production migration, deployment, merge, destructive operation, or scope expansion.

## Completion evidence

- Commit: recorded after local validation.
- PR: required before merge.
- CI run(s): exact PR head SHA only.
- Observed final status: must be verified, never inferred.
- Known limitations: v1 does not generate patches; governed execution is limited to explicit Ruff commands, the attempt ledger is process-local for v1, and the executor never bypasses task scope.
