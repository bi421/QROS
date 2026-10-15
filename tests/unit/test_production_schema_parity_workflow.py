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
