## Change

### Purpose
<!-- What problem does this PR solve? -->

### Scope
- [ ] SaaS runtime
- [ ] Research core
- [ ] Database / RLS
- [ ] Security / supply chain
- [ ] Packaging / release
- [ ] Git / governance
- [ ] Documentation

### Verification

- Exact PR head SHA:
- Base `main` SHA:
- Tests / checks run:
- Environment verification (if applicable):

### Risk

- [ ] No production runtime change
- [ ] No database change
- [ ] No authentication / authorization change
- [ ] No tenant-boundary change
- [ ] No secret / credential change

If any box above is unchecked, explain the impact and required gates.

### Evidence boundary

CI evidence proves the exact commit checked by CI. It does not by itself prove production deployment, live authentication, database migration state, backup/restore, or public SaaS behavior.

### Rollback

<!-- State how this change can be reverted or rolled back. -->

### Final checklist

- [ ] Branch is short-lived and contains one coherent change
- [ ] PR title follows Conventional Commits
- [ ] Exact head SHA has been verified
- [ ] Applicable tests and security gates pass
- [ ] No unrelated files or cleanup are included
- [ ] Documentation is updated where the contract changed
