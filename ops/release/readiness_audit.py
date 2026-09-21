"""Static release-readiness contract checks for QROS.

This gate verifies that the repository retains the operational controls required
for an environment-backed release. It deliberately does not claim that staging
or production execution has occurred.
"""

from pathlib import Path

REQUIRED_FILES = (
    ".github/workflows/production-db-backup.yml",
    ".github/workflows/production-schema-parity.yml",
    ".github/workflows/staging-release-gate.yml",
    ".github/workflows/staging-performance-gate.yml",
    ".github/workflows/storage-recovery-drill.yml",
    "docs/operations/PRODUCTION_RECOVERY_CONTROLS_V1.md",
)

REQUIRED_MARKERS = {
    ".github/workflows/production-db-backup.yml": (
        "workflow_dispatch",
        "pg_dump",
        "aws s3 cp",
        "head-object",
    ),
    ".github/workflows/production-schema-parity.yml": (
        "workflow_dispatch",
        "supabase migration list --linked",
        "supabase db push --linked --dry-run",
        "relrowsecurity",
    ),
    ".github/workflows/staging-release-gate.yml": (
        "workflow_dispatch",
        "/healthz",
        "/readyz",
        "/v1/me",
    ),
    ".github/workflows/staging-performance-gate.yml": (
        "workflow_dispatch",
        "p95",
        "max-error-rate",
    ),
    ".github/workflows/storage-recovery-drill.yml": (
        "workflow_dispatch",
        "sha256",
        "cmp",
        "qros-datasets",
    ),
    "docs/operations/PRODUCTION_RECOVERY_CONTROLS_V1.md": (
        "RPO/RTO",
        "Release blockers",
        "exact-release smoke",
    ),
}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    failures: list[str] = []

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            failures.append(f"missing required release-control file: {relative}")
            continue

        text = path.read_text(encoding="utf-8")
        for marker in REQUIRED_MARKERS[relative]:
            if marker.lower() not in text.lower():
                failures.append(
                    f"missing required marker in {relative}: {marker!r}"
                )

    if failures:
        print("release_readiness_static=FAIL")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("release_readiness_static=PASS")
    print(f"verified_files={len(REQUIRED_FILES)}")
    print("environment_execution_status=NOT_CLAIMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
