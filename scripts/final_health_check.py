#!/usr/bin/env python3
"""Final health check for exact release gate."""

import json
import subprocess
import sys
from datetime import datetime, timezone


def run_check(name, cmd):
    """Run a health check command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main():
    db_url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://localhost/postgres"

    health = {
        "authz": run_check("authz", f"python scripts/verify_authz.py {db_url}"),
        "backup_restore": run_check("backup_restore", f"python scripts/backup_verify.py {db_url}"),
        "tenant_isolation": run_check(
            "tenant_isolation",
            "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock public.ecr.aws/supabase/pg_prove:3.36 supabase/tests/tenant_isolation_test.sql",
        ),
    }

    passed = all(h["status"] == "PASS" for h in health.values())

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health": health,
        "health_status": "PASS" if passed else "FAIL",
    }

    print(json.dumps(result, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
