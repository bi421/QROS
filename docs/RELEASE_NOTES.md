# ResearchOS Release Notes

**Latest Release:** v1.0.1 (Release Candidate)
**Release Date:** 2026-10-08
**Status:** Release Candidate

---

## v1.0.1 — Patch Release Candidate (2026-08-16)

**Status:** Release Candidate

### Scope

v1.0.1 is a non-breaking patch release focused on:

- Decision Engine contract hardening
- Regression coverage
- Repository hygiene
- Release metadata consistency
- Removal of tracked local database artifacts

### Verification

The release candidate was verified with:

- **3,283 tests passed**
- **7 tests skipped**
- **0 test failures**
- **Ruff:** clean
- **Full test suite:** successful
- **Decision Engine:** regression coverage verified
- **Database tracking:** production `.db` files removed from Git tracking
- **Database ignore rule:** `*.db` verified
- **Release version:** `1.0.1`

### Repository Hygiene

The following local artifacts were excluded from the repository:

- `coverage_run_new.log`
- `decision_engine_full_dump.txt`
- `diagnosis.txt`
- Local SQLite database files (`*.db`)

The local database files remain on disk where required for development/testing, but are no longer tracked by Git.

### Git State

Current development HEAD:

`584cd7bfe13bfdd62f67a93eef96206646c798e0`

Commit:

`chore(quant): remove obsolete engine surfaces (#607)`

The release candidate has **not** yet been tagged or pushed.

### Release Status

**v1.0.1 is a Release Candidate only.**

No production release action has been performed.

The following actions remain intentionally pending:

- Commit final release changes
- Create `v1.0.1` tag
- Push commit and tag to origin
- Final remote verification

---

## v1.0.0 — Production-Ready (2026-08-16)

**Stability:** Stable

### Foundation & Security

- Removed hardcoded secrets
- Architecture enforcement
- Environment-variable-backed configuration
- Branch tracking and merge history

### Evidence & Lineage

- Evidence Repository
- Lineage Query Engine
- Artifact emission
- Deterministic reproduction engine
- Evidence-layer validation

### Validation

- Full test isolation
- Walk-forward validation
- Leakage detection
- Architecture guard tests
- Deterministic execution

### Documentation

- README
- AI_CONTEXT.md
- CHANGELOG.md
- Phase documentation
- Test baseline and isolation documentation

---

## Future Roadmap

### v1.1.0 — Feature & Model Registry (Planned)

Planned capabilities:

- Feature Registry
- Model Registry
- Experiment Comparison
- Additional research metadata and provenance capabilities

### v1.2.0 — Risk & Knowledge (Planned)

Planned capabilities:

- Risk Analytics
- Knowledge Graph
- Reports Generator

### v1.3.0+ — Search & UI (Planned)

Planned capabilities:

- Search Interface
- Dashboard
- Archive/Lifecycle management

---

## Release History

| Version | Date | Phase | Status | Notes |
|---|---|---|---|---|
| v1.0.1 | 2026-08-16 | Patch | RC | Decision Engine hardening, regression coverage, repository hygiene |
| v1.0.0 | 2026-08-16 | 0-5 Complete | Stable | Production-ready baseline |
| v1.0.0-rc1 | TBD | 0-3 Complete | Archived | Pre-release candidate |
| v0.x.x | Early 2026 | Development | Archived | Early-stage development |

---

## Upgrading

### From v1.0.0 to v1.0.1

No breaking API changes are intended.

v1.0.1 is a patch release candidate focused on hardening, regression coverage, repository hygiene, and release consistency.

### From v1.0.x to v1.1.0

New backward-compatible capability layers are planned.

### From v1.x to v2.0.0

Major breaking changes may be introduced. A migration guide will accompany the future v2.0.0 release candidate.

---

## Release Procedure

Before declaring v1.0.1 stable:

1. Confirm all tests pass.
2. Confirm Ruff is clean.
3. Confirm release metadata is consistent.
4. Confirm no local database files are tracked.
5. Review the final working tree.
6. Commit the release changes.
7. Create the `v1.0.1` tag.
8. Push the commit and tag.
9. Verify the remote repository and tag.

---

**Last Updated:** 2026-08-16
**Status:** Release Candidate
**Next Review:** Before v1.0.1 final release
