# SaaS Git Governance

## Integration model

- `main` is the only integration branch.
- Every change enters through a pull request from a short-lived branch.
- Branch names use `<type>/<short-description>`.
- Pull request titles use Conventional Commit syntax.
- CI evidence must correspond to the exact commit under review.
- Production claims require environment-specific evidence; green repository CI alone is insufficient.

## SaaS-sensitive review surfaces

Changes under these paths require explicit owner review through CODEOWNERS:

- `.github/`
- `supabase/`
- `researchos/saas/`
- `scripts/`
- `docs/saas/`
- `todo/saas.md`

## Merge discipline

1. Start from current `main`.
2. Make one coherent change per branch/PR.
3. Keep the PR diff reviewable; do not mix stale cleanup with new SaaS work.
4. Require all applicable CI/security checks to pass on the exact PR head.
5. Merge only after review and green checks.
6. Delete the merged branch.
7. Re-verify `main` after merge and record the exact SHA.

## Production evidence rule

A repository state is not called production-ready merely because GitHub Actions is green. Deployment SHA, database migration state, backup/restore evidence, public HTTPS, authentication, and SaaS golden-path behavior must be verified in the target environment.

## Local working-tree rule

Never reset, stash, clean, or overwrite a dirty developer branch as part of GitHub governance work. Repository governance changes must be made on a fresh branch from `main`.
