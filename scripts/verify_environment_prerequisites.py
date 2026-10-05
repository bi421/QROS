#!/usr/bin/env python3
"""Fail-closed preflight checks for externally provisioned QROS gates.

This utility validates prerequisite presence and identity relationships without
printing secret values or claiming that the target environment is reachable.
It is intentionally limited to deterministic configuration checks.
"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

PROFILES: dict[str, tuple[str, ...]] = {
    "staging": (
        "QROS_STAGING_BASE_URL",
        "QROS_STAGING_JWT",
        "QROS_STAGING_ISOLATION_JWT",
    ),
    "dr": (
        "QROS_BACKUP_SOURCE_ENVIRONMENT",
        "QROS_STAGING_SUPABASE_PROJECT_REF",
        "QROS_STAGING_SUPABASE_URL",
        "QROS_STAGING_SUPABASE_SERVICE_ROLE_KEY",
        "QROS_RECOVERY_TARGET_ENVIRONMENT",
        "QROS_RECOVERY_TARGET_ID",
        "QROS_RECOVERY_S3_BUCKET",
        "QROS_RECOVERY_AWS_REGION",
        "QROS_RECOVERY_AWS_ACCESS_KEY_ID",
        "QROS_RECOVERY_AWS_SECRET_ACCESS_KEY",
    ),
    "production-migration": (
        "SUPABASE_ACCESS_TOKEN",
        "PRODUCTION_DB_PASSWORD",
        "PRODUCTION_PROJECT_ID",
    ),
}


def _required(profile: str) -> list[str]:
    missing = [name for name in PROFILES[profile] if not os.environ.get(name, "").strip()]
    if missing:
        raise SystemExit(
            f"{profile} preflight failed: missing required variables: "
            + ", ".join(missing)
        )
    return list(PROFILES[profile])


def _validate_staging() -> None:
    value = os.environ["QROS_STAGING_BASE_URL"].strip()
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit(
            "staging preflight failed: QROS_STAGING_BASE_URL must be a bare HTTPS origin without credentials, query, or fragment"
        )
    if os.environ["QROS_STAGING_JWT"].strip() == os.environ["QROS_STAGING_ISOLATION_JWT"].strip():
        raise SystemExit(
            "staging preflight failed: primary and isolation JWTs must be distinct controlled identities"
        )


def _validate_dr() -> None:
    if os.environ["QROS_BACKUP_SOURCE_ENVIRONMENT"].strip().lower() != "staging":
        raise SystemExit("DR preflight failed: recovery source environment must be staging")
    target_env = os.environ["QROS_RECOVERY_TARGET_ENVIRONMENT"].strip().lower()
    if target_env in {"staging", "production", "prod"}:
        raise SystemExit(
            "DR preflight failed: recovery target environment must be isolated from staging and production"
        )
    if (
        os.environ["QROS_RECOVERY_TARGET_ID"].strip()
        == os.environ["QROS_STAGING_SUPABASE_PROJECT_REF"].strip()
    ):
        raise SystemExit(
            "DR preflight failed: recovery target identity must differ from staging project identity"
        )


def _validate_production_migration() -> None:
    if os.environ["PRODUCTION_PROJECT_ID"].strip() != "pvhdsngxyoiqhqwujfjt":
        raise SystemExit(
            "production-migration preflight failed: PRODUCTION_PROJECT_ID does not match the governed QROS production target"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    args = parser.parse_args()

    names = _required(args.profile)
    if args.profile == "staging":
        _validate_staging()
    elif args.profile == "dr":
        _validate_dr()
    else:
        _validate_production_migration()

    print(f"{args.profile}_preflight=PASS")
    print("checked_variables=" + str(len(names)))
    print("secret_values=NOT_PRINTED")
    print("target_reachability=NOT_CLAIMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
