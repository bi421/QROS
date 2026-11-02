from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20261102000100_default_privileges_hardening.sql"


def test_default_privilege_migration_respects_supabase_managed_role_boundary() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"ALTER DEFAULT PRIVILEGES FOR ROLE postgres", sql, re.IGNORECASE)
    assert not re.search(
        r"ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin|SET ROLE supabase_admin",
        sql,
        re.IGNORECASE,
    )
    assert "platform-managed" in sql


def test_public_function_execute_default_is_revoked_globally() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER DEFAULT PRIVILEGES FOR ROLE postgres\s+REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
        sql,
        re.IGNORECASE,
    )
