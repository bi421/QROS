# QROS Engineering Agent Contract v1

Status: ACTIVE

## Purpose

This contract defines the safety boundary for AI-assisted changes to QROS. An agent may plan, edit, test, repair, and prepare a pull request, but it must not bypass deterministic validation or silently widen task scope.

## Required lifecycle

1. Read the task contract.
2. Inspect the current repository state and relevant implementation.
3. Change only files allowed by the task contract.
4. Run the required local validation gates.
5. Inspect the final diff for scope and contract compliance.
6. Commit only after local validation passes.
7. Open or update a pull request.
8. Treat GitHub CI as authoritative for repository-wide compatibility, native builds, integration, and full coverage.
9. If CI fails, classify the failure before changing code.
10. Repair only within the task scope and retry within the configured attempt limit.
11. Stop and escalate when the failure is ambiguous, the scope must expand, or the attempt limit is exhausted.

## Non-negotiable invariants

- Never weaken, delete, skip, or reinterpret a test merely to obtain a green result.
- Never change production migrations, authentication, authorization, tenant isolation, or destructive operations unless explicitly included in the task contract.
- Never claim a gate passed without observed evidence.
- Never treat an empty CI status response as proof of success.
- Preserve deterministic and fail-closed behavior.
- Prefer the smallest change that satisfies the stated contract.
- Keep one logical change per commit when practical.

## Task contract

Every autonomous task must declare:

- goal
- allowed files or paths
- forbidden files or paths
- preconditions
- acceptance criteria
- required validation
- security/data-integrity impact
- migration impact
- maximum repair attempts
- escalation conditions

## Validation hierarchy

The existing repository gates are reused rather than duplicated:

- pre-commit: formatting, Ruff, text integrity, scope guard
- scripts/preflight.py: dependency-aware targeted/frozen/full pytest selection
- GitHub CI: repository integrity, Python compatibility, native build, container smoke test, database isolation

An agent must not replace these gates with an ad-hoc weaker equivalent.

## Repair policy

A repair agent receives the observed failure, relevant logs, task contract, and current diff. It must first classify the failure as one of:

- implementation defect
- test/contract mismatch
- formatting/static failure
- environment/tooling failure
- CI orchestration failure
- missing prerequisite
- ambiguous/unsafe

Only the first four categories are normally repairable without human escalation. CI orchestration failures and ambiguous/unsafe cases must not trigger speculative source changes.

## Human approval boundary

Human approval remains required for:

- merging protected production changes
- production migrations
- production deployment
- destructive data operations
- changes that expand security or tenant-isolation scope
- unresolved or repeated autonomous failures

The objective is controlled autonomy, not uncontrolled self-modification.