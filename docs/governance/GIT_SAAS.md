# SaaS Git Governance

## Repository state model

QROS uses a single protected integration branch:

- `main` is the only integration branch.
- No feature, diagnostic, audit, or release work is committed directly to `main`.
- Every change enters through a short-lived pull request branch.
- A PR must be based on current `main` and validated at its exact head SHA.
- A merged PR is integrated only after `main` is re-read and its resulting SHA is recorded.

## Branch lifecycle

Use one branch for one coherent change.

Allowed prefixes:

- `feat/`
- `fix/`
- `docs/`
- `test/`
- `refactor/`
- `perf/`
- `build/`
- `ci/`
- `chore/`
- `revert/`

Branch names must be lowercase and descriptive. Dated/versioned suffixes are reserved for genuinely dated forensic or audit artifacts.

Lifecycle:

1. Create from current `main`.
2. Keep one coherent change per branch.
3. Open a PR with a Conventional Commit title.
4. Verify the exact PR head SHA.
5. Require applicable CI, security, and ownership checks.
6. Merge through the PR.
7. Delete the merged branch automatically.
8. Re-read `main`, record its new SHA, and start the next change from that SHA.

Do not reuse an old branch for unrelated work.

## Pull request discipline

PR titles use:

`type(optional-scope): description`

Examples:

- `feat(saas): provision customer workspace`
- `fix(packaging): make CLI entrypoints installable`
- `ci(security): add fail-closed dependency scanning`

Keep governance, packaging, SaaS runtime, database migrations, and research changes separate unless they are inseparable parts of one change.

Evidence must correspond to the exact PR head under review.

## Required merge gates

For SaaS-sensitive changes, the merge decision must account for:

- Git Governance
- CODEOWNERS review where applicable
- applicable Python test/type/property gates
- supply-chain/security checks
- database/RLS checks for database changes
- release-readiness checks
- exact-head verification

Green repository CI is not, by itself, production-readiness evidence.

## Protected main requirements

GitHub repository settings should enforce:

- pull request required for changes;
- required status checks;
- required CODEOWNERS review for owned paths;
- force pushes disabled;
- deletion disabled for `main`;
- stale approvals dismissed when the protected diff changes, where supported;
- conversation resolution required where supported.

These are repository settings, not CI claims. Verify them in GitHub settings before treating them as active controls.

## Branch cleanup

Merged branches are disposable integration artifacts and are deleted automatically by the merged-branch cleanup workflow.

Do not delete an unmerged branch merely because it is old. First establish whether it contains unique work, an open PR, or an evidence/audit artifact that must be retained.

Historical diagnostic branches may be retained temporarily when referenced by an audit record, but they are not active integration branches.

## SaaS-sensitive ownership

The following paths require explicit CODEOWNERS review:

- `.github/`
- `supabase/`
- `researchos/saas/`
- `scripts/`
- `docs/saas/`
- `todo/saas.md`

## Local working-tree safety

GitHub governance work must never reset, stash, clean, overwrite, or checkout a dirty developer working tree.

Repository governance changes are made from a fresh branch created from `main`.

## Production evidence boundary

Repository CI proves repository state only.

A production claim additionally requires environment-specific evidence for the relevant target, including deployment SHA, database migration state, backup/restore evidence, public HTTPS, authentication, and SaaS golden-path behavior.

Never convert `CI PASS` into `production verified` without target-environment evidence.
