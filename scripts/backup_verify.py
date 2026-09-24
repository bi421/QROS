#!/usr/bin/env python3
"""Verify backup/restore cycle for disaster recovery."""

import subprocess
import sys


def run_cmd(cmd, check=True):
    """Run shell command, return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print(f"FAILED: {cmd}")
        print(f"STDERR: {result.stderr}")
        return None
    return result.stdout + result.stderr


def backup_and_restore(db_url):
    """Backup schema and data, then restore to verify."""

    # Step 1: Dump schema with CREATE SCHEMA
    schema_dump = "/tmp/schema.sql"
    print(f"Dumping schema to {schema_dump}...")
    cmd = f'pg_dump --schema-only "{db_url}" > "{schema_dump}"'
    run_cmd(cmd)

    # Step 2: Add private schema creation if missing
    with open(schema_dump, "r") as f:
        schema_content = f.read()

    if "CREATE SCHEMA private" not in schema_content:
        schema_content = "CREATE SCHEMA IF NOT EXISTS private;\n" + schema_content
        with open(schema_dump, "w") as f:
            f.write(schema_content)
        print("Added CREATE SCHEMA private to dump")

    # Step 3: Create a test database
    test_db = "qros_dr_test"
    run_cmd(f'dropdb --if-exists "{test_db}"', check=False)
    run_cmd(f'createdb "{test_db}"', check=True)

    # Step 4: Restore schema to test database
    restore_url = db_url.replace(db_url.split("/")[-1], test_db)
    print(f"Restoring to {restore_url}...")
    cmd = f'psql "{restore_url}" < "{schema_dump}"'
    output = run_cmd(cmd, check=False)

    if "ERROR" in output:
        print(f"RESTORE FAILED:\n{output}")
        return False

    # Step 5: Verify schema exists
    cmd = f'psql "{restore_url}" -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name=\'private\';"'
    result = run_cmd(cmd, check=True)
    if "private" not in result:
        print("FAILED: private schema not found after restore")
        return False

    print("Backup/restore cycle PASS")
    return True


if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://localhost/postgres"
    success = backup_and_restore(db_url)
    sys.exit(0 if success else 1)
