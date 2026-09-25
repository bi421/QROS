"""Static release-readiness contract checks for QROS.

This gate verifies that the repository retains the operational controls required
for an environment-backed release. It deliberately does not claim that staging
or production execution has occurred.
"""

import re
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
        "scripts/ci/production_schema_parity.sh",
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



def check_release_metadata(root: Path, failures: list[str]) -> None:
    version_paths = (
        root / "scripts" / "version.py",
        root / "researchos" / "version.py",
    )
    versions: list[tuple[str, str, str]] = []
    for path in version_paths:
        if not path.is_file():
            failures.append(f"missing release metadata file: {path.relative_to(root)}")
            continue
        text = path.read_text(encoding="utf-8")
        version_match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
        status_match = re.search(r'^STATUS\s*=\s*"([^"]+)"', text, re.MULTILINE)
        codename_match = re.search(r'^VERSION_CODENAME\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if not (version_match and status_match and codename_match):
            failures.append(f"incomplete release metadata: {path.relative_to(root)}")
            continue
        versions.append(
            (version_match.group(1), status_match.group(1), codename_match.group(1))
        )

    if len(versions) != len(version_paths):
        return
    if len(set(versions)) != 1:
        failures.append("scripts/version.py and researchos/version.py disagree")
        return

    version, status, codename = versions[0]
    release_notes = root / "docs" / "RELEASE_NOTES.md"
    if not release_notes.is_file():
        failures.append("missing release notes: docs/RELEASE_NOTES.md")
        return

    lines = release_notes.read_text(encoding="utf-8").splitlines()[:12]
    latest_version = next(
        (line.split("v", 1)[1].split()[0]
         for line in lines if line.startswith("**Latest Release:** v")),
        None,
    )
    latest_status = next(
        (line[len("**Status:** "):].strip()
         for line in lines if line.startswith("**Status:** ")),
        None,
    )
    if latest_version is None or latest_status is None:
        failures.append("release notes do not declare latest version/status")
        return
    if latest_version != version:
        failures.append(
            f"release notes version v{latest_version} != code version {version}"
        )

    expected_status = {
        "release-candidate": "Release Candidate",
        "stable": "Stable",
    }.get(status)
    if expected_status is None:
        failures.append(f"unsupported release STATUS: {status}")
    elif latest_status != expected_status:
        failures.append(
            f"release notes status {latest_status!r} != code status {expected_status!r}"
        )
    if status == "release-candidate" and codename != "Release-Candidate":
        failures.append(
            f"release-candidate status requires VERSION_CODENAME=Release-Candidate, got {codename!r}"
        )

def main() -> int:
    root = Path(__file__).resolve().parents[2]
    failures: list[str] = []

    check_release_metadata(root, failures)

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
