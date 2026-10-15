from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "staging-golden-path-gate.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_staging_storage_gate_requires_separate_staging_and_production_urls():
    source = workflow_text()

    assert 'QROS_STAGING_SUPABASE_URL: ${{ secrets.QROS_STAGING_SUPABASE_URL }}' in source
    assert 'QROS_PRODUCTION_SUPABASE_URL: ${{ secrets.QROS_PRODUCTION_SUPABASE_URL }}' in source
    assert 'QROS_STAGING_SUPABASE_ANON_KEY: ${{ secrets.QROS_STAGING_SUPABASE_ANON_KEY }}' in source
    assert 'test -n "${QROS_STAGING_SUPABASE_URL}"' in source
    assert 'test -n "${QROS_PRODUCTION_SUPABASE_URL}"' in source
    assert 'test -n "${QROS_STAGING_SUPABASE_ANON_KEY}"' in source


def test_staging_storage_gate_requires_https_and_distinct_hosts():
    source = workflow_text()

    assert 'staging.scheme != "https"' in source
    assert 'production.scheme != "https"' in source
    assert 'if staging_host == production_host:' in source
    assert 'must not target the production Supabase host' in source


def test_dataset_storage_path_is_workspace_and_content_addressed():
    source = workflow_text()

    assert 'storage_path="$(jq -er \'.version.storage_path\'' in source
    assert 'expected_storage_path="tenant/${workspace_id}/datasets/${expected_sha}/1/"' in source
    assert 'test "${storage_path}" = "${expected_storage_path}"' in source


def test_storage_owner_read_must_match_fixture_sha256():
    source = workflow_text()

    assert '/storage/v1/object/authenticated/qros-datasets/${storage_path}' in source
    assert 'Authorization: Bearer ${QROS_JWT}' in source
    assert 'storage_owner_sha="$(sha256sum "${work}/storage-owner.bin"' in source
    assert 'test "${storage_owner_sha}" = "${expected_sha}"' in source


def test_cross_workspace_storage_read_fails_if_object_is_accessible():
    source = workflow_text()

    assert 'Authorization: Bearer ${QROS_ISOLATION_JWT}' in source
    assert '200|206)' in source
    assert 'cross-workspace Storage read unexpectedly succeeded' in source
    assert '400|401|403|404)' in source
    assert 'unexpected cross-workspace Storage response HTTP' in source


def test_storage_isolation_outcome_is_recorded_in_evidence_artifact():
    source = workflow_text()

    assert '"owner_read": "verified_sha256_match"' in source
    assert '"cross_workspace_read": "verified_denied_http_${storage_other_status}"' in source
    assert '"private_storage": "verified_denied"' in source
