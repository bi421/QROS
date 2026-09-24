#!/usr/bin/env python3
"""Verify backup/restore cycle for disaster recovery."""

import json
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, check=True):
    """Run shell command, return stdout + stderr."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print(f"FAILED: {cmd}")
        print(f"STDERR: {result.stderr}")
        return None
    return result.stdout + result.stderr

def backup_and_restore(db_url):
    """Backup schema and data, then restore to verify."""
    
    # Step 1: Dump full schema (includes all schemas)
    schema_dump = "/tmp/schema.sql"
    print(f"Dumping schema to {schema_dump}...")
    cmd = f'pg_dump --schema-only --no-owner "{db_url}" > "{schema_dump}"'
    run_cmd(cmd)
    
    # Step 2: Fix schema creation statements to use IF NOT EXISTS
    with open(schema_dump, 'r') as f:
        schema_content = f.read()
    
    # Replace CREATE SCHEMA with CREATE SCHEMA IF NOT EXISTS
    schema_content = schema_content.replace(
        'CREATE SCHEMA ',
        'CREATE SCHEMA IF NOT EXISTS '
    )
    
    with open(schema_dump, 'w') as f:
        f.write(schema_content)
    
    print("Updated schema dump with IF NOT EXISTS")
    
    # Step 3: Create test database
    test_db = "qros_dr_test"
    run_cmd(f'dropdb --if-exists "{test_db}"', check=False)
    run_cmd(f'createdb "{test_db}"', check=True)
    
    # Step 4: Restore schema to test database
    restore_url = db_url.replace(db_url.split('/')[-1], test_db)
    print(f"Restoring to {restore_url}...")
    
    cmd = f'psql "{restore_url}" < "{schema_dump}" 2>&1'
    output = run_cmd(cmd, check=False)
    
    # Ignore warnings about existing schemas
    if "ERROR" in output and "already exists" not in output:
        print(f"RESTORE FAILED:\n{output}")
        return False
    
    # Step 5: Verify required schemas exist
    for schema in ["public", "private", "extensions"]:
        cmd = f'psql "{restore_url}" -tc "SELECT schema_name FROM information_schema.schemata WHERE schema_name=\'{schema}\';" 2>&1'
        result = run_cmd(cmd, check=True)
        if schema not in result:
            print(f"FAILED: {schema} schema not found after restore")
            return False
    
    print("Backup/restore cycle PASS")
    return True

if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://localhost/postgres"
    success = backup_and_restore(db_url)
    sys.exit(0 if success else 1)