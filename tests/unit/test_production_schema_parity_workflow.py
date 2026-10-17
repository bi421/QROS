from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'production-schema-parity.yml'


def source() -> str:
    return WORKFLOW.read_text(encoding='utf-8')


def test_production_parity_gate_rejects_invalid_supabase_access_token_format():
    text = source()
    assert 'case "${SUPABASE_ACCESS_TOKEN}" in' in text
    assert 'sbp_*) ;;' in text
    assert 'unsupported format' in text
    assert 'beginning with sbp_' in text


def test_production_parity_gate_pins_governed_production_project_ref():
    text = source()
    assert 'test "${SUPABASE_PROJECT_ID}" = "pvhdsngxyoiqhqwujfjt"' in text
    assert 'does not match the documented governed QROS production project ref' in text


def test_production_parity_gate_uses_only_dry_run_for_migration_preview():
    text = source()
    assert 'supabase db push --linked --dry-run' in (ROOT / 'scripts' / 'ci' / 'production_schema_parity.sh').read_text(encoding='utf-8')
    assert 'supabase db push --linked\n' not in text



def _run_migration_parity_fixture(text: str):
    import subprocess
    import sys

    checker = ROOT / 'scripts' / 'ci' / 'check_migration_history_parity.py'
    return subprocess.run(
        [sys.executable, str(checker)], input=text, capture_output=True, text=True, check=False
    )


def test_migration_parity_parser_accepts_12_and_14_digit_versions():
    fixture = """Local | Remote | Time (UTC)
------------|------------|-----------
202610060001 | 202610060001 | 2026-10-06 00:01:00
20261010000100 | 20261010000100 | 2026-10-10 00:01:00
"""
    result = _run_migration_parity_fixture(fixture)
    assert result.returncode == 0, result.stderr
    assert 'verified 2 migration version rows' in result.stdout


def test_migration_parity_parser_fails_on_missing_or_different_remote_versions():
    missing_remote = "Local | Remote | Time (UTC)\n202610060001 | |\n"
    result = _run_migration_parity_fixture(missing_remote)
    assert result.returncode == 1
    assert 'local=202610060001 remote=<missing>' in result.stdout

    mismatch = "Local | Remote | Time (UTC)\n202610060001 | 202610060002 |\n"
    result = _run_migration_parity_fixture(mismatch)
    assert result.returncode == 1
    assert 'local=202610060001 remote=202610060002' in result.stdout
