import pytest
from pydantic import ValidationError

from app.config import Settings


def test_list_settings_accept_json_or_comma_separated_environment(monkeypatch) -> None:
    monkeypatch.setenv("OIDC_ALGORITHMS", "RS256")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://portal.example")
    monkeypatch.setenv("ALLOWED_HOSTS", '["portal.example","internal.example"]')

    settings = Settings(_env_file=None)

    assert settings.oidc_algorithms == ["RS256"]
    assert settings.allowed_origins == ["https://portal.example"]
    assert settings.allowed_hosts == ["portal.example", "internal.example"]


def production_values() -> dict:
    return {
        "app_env": "production",
        "database_url": "postgresql+asyncpg://fixture:fixture@db.internal/fixture",
        "auto_create_schema": False,
        "dev_auth_enabled": False,
        "allowed_origins": ["https://portal.example"],
        "allowed_hosts": ["api.internal"],
        "oidc_issuer": "portal",
        "oidc_audience": "api",
        "oidc_public_key": "synthetic-key",
        "otel_exporter_otlp_endpoint": "https://collector.internal/v1/traces",
        "secret_provider": "aws",
        "secrets_aws_region": "ap-northeast-2",
    }


def test_managed_vercel_request_logs_can_replace_external_otlp():
    values = production_values()
    values.update(
        secret_provider="vercel",
        telemetry_backend="vercel_logs",
        vercel="1",
        vercel_env="production",
        vercel_project_id="test-project",
        otel_exporter_otlp_endpoint=None,
    )
    assert Settings(_env_file=None, **values).telemetry_backend == "vercel_logs"
    values["database_url"] = "sqlite+aiosqlite:///local.db"
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"debug": True}, "DEBUG"),
        ({"database_url": "sqlite+aiosqlite:///local.db"}, "DATABASE_URL"),
        ({"database_url": "postgresql://db.internal/"}, "DATABASE_URL"),
        ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": ["*.example.com"]}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": []}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": ["https://api.example"]}, "ALLOWED_HOSTS"),
        ({"allowed_origins": ["http://portal.example"]}, "HTTPS origins"),
        ({"allowed_origins": ["https://portal.example/path"]}, "HTTPS origins"),
        ({"allowed_origins": ["https://user:password@portal.example"]}, "HTTPS origins"),
        ({"allowed_origins": ["https://*.example"]}, "HTTPS origins"),
        ({"oidc_algorithms": ["RS256", "HS256"]}, "OIDC_ALGORITHMS"),
        ({"oidc_algorithms": []}, "OIDC_ALGORITHMS"),
        ({"oidc_jwks_url": "http://identity.example/keys"}, "OIDC_JWKS_URL"),
        ({"oidc_jwks_url": "https://user:password@identity.example/keys"}, "OIDC_JWKS_URL"),
        ({"otel_exporter_otlp_endpoint": "http://collector/v1/traces"}, "HTTPS endpoint"),
        ({"otel_exporter_otlp_endpoint": "https:///v1/traces"}, "HTTPS endpoint"),
        ({"otel_exporter_otlp_endpoint": "https://collector/v1/traces#fragment"}, "HTTPS endpoint"),
        (
            {
                "smtp_enabled": True,
                "smtp_host": "mail.internal",
                "smtp_from_email": "alerts@example.com",
                "smtp_starttls": False,
            },
            "SMTP requires TLS",
        ),
    ],
)
def test_production_rejects_unsafe_configuration(overrides: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **(production_values() | overrides))


def test_production_accepts_exact_hosts_and_tls_endpoints() -> None:
    settings = Settings(
        _env_file=None,
        **production_values(),
        oidc_jwks_url="https://identity.example/keys",
    )
    assert settings.allowed_hosts == ["api.internal"]


def test_local_development_retains_loopback_http_configuration() -> None:
    settings = Settings(_env_file=None, app_env="local", allowed_hosts=["*"])
    assert settings.allowed_origins == ["http://localhost:3000"]


def test_vercel_provider_requires_deployment_metadata() -> None:
    values = production_values() | {"secret_provider": "vercel"}
    with pytest.raises(ValidationError, match="Vercel deployment metadata"):
        Settings(_env_file=None, **values)
    settings = Settings(
        _env_file=None,
        **(
            values
            | {
                "vercel": "1",
                "vercel_env": "production",
                "vercel_project_id": "prj_fixture",
            }
        ),
    )
    assert settings.secret_provider == "vercel"


def test_invalid_configuration_does_not_echo_secret_inputs() -> None:
    secret = "sensitive-fixture-that-must-not-appear"
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            **(
                production_values()
                | {
                    "secret_provider": "environment",
                    "gemini_api_key": secret,
                }
            ),
        )
    assert secret not in str(error.value)
