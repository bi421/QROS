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
    "scripts/ci/production_schema_parity.sh",
)

REQUIRED_MARKERS = {
    ".github/workflows/production-db-backup.yml": (
        "workflow_dispatch",
        "pg_dump",
        "aws s3 cp",
        "head-object",
        "sha256sum --check",
        "BACKUP_AWS_ACCESS_KEY_ID",
        "BACKUP_AWS_SECRET_ACCESS_KEY",
        "BACKUP_AWS_REGION",
        "PROD_DATABASE_URL",
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
        "qros-storage-drill/$OBJECT_NAME",
        "aws s3api head-object",
        "QROS_RECOVERY_AWS_ACCESS_KEY_ID",
        "QROS_RECOVERY_AWS_SECRET_ACCESS_KEY",
        "QROS_RECOVERY_AWS_REGION",
    ),
    "docs/operations/PRODUCTION_RECOVERY_CONTROLS_V1.md": (
        "RPO/RTO",
        "Release blockers",
        "exact-release smoke",
    ),
    "scripts/ci/production_schema_parity.sh": (
        "supabase migration list --linked",
        "supabase db push --linked --dry-run",
        "relrowsecurity",
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

        lines = text.splitlines()
        if any(line == "    env:" for line in lines):
            failures.append(
                f"forbidden job-level env block in {relative}"
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
