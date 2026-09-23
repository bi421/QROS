from __future__ import annotations

from uuid import uuid4

from researchos.saas.storage.signed_urls import bind_signed_url, verify_signed_url


def test_signed_url_is_bound_to_tenant_and_expires_in_3600(monkeypatch) -> None:
    monkeypatch.setenv("QROS_STORAGE_SIGNING_SECRET", "test-secret")
    tenant_a = uuid4()
    tenant_b = uuid4()
    path = f"tenant/{tenant_a}/datasets/{'a' * 64}/1"
    provider = "https://storage.example/signed"

    signed = bind_signed_url(provider, tenant_a, path, now=1000)

    assert "tenant_id=" + str(tenant_a) in signed
    assert "expires=4600" in signed
    assert verify_signed_url(signed, tenant_a, path, now=4599)
    assert not verify_signed_url(signed, tenant_b, path, now=4599)
    assert not verify_signed_url(signed, tenant_a, f"tenant/{tenant_a}/datasets/{'b' * 64}/1", now=4599)
    assert not verify_signed_url(signed, tenant_a, path, now=4601)
