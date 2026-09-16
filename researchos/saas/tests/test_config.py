import pytest

from researchos.saas.config import ConfigurationError, SaaSSettings


def test_development_settings_have_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCHOS_ENV", raising=False)
    monkeypatch.delenv("RESEARCHOS_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    settings = SaaSSettings.from_env()

    assert settings.environment == "development"
    assert settings.auth_required is False
    assert settings.max_request_body_bytes == 10_000_000
    assert settings.rate_limit_per_minute == 60


def test_production_requires_supabase_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCHOS_ENV", "production")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_URL"):
        SaaSSettings.from_env()


def test_invalid_boolean_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCHOS_AUTH_REQUIRED", "sometimes")

    with pytest.raises(ConfigurationError, match="RESEARCHOS_AUTH_REQUIRED"):
        SaaSSettings.from_env()


def test_production_requires_server_side_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCHOS_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_SERVICE_ROLE_KEY"):
        SaaSSettings.from_env()


def test_production_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCHOS_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")

    settings = SaaSSettings.from_env()

    assert settings.environment == "production"
    assert settings.auth_required is True
    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_service_role_key == "service-role-test-key"
