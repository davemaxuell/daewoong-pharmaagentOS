from app.config import Settings


def test_list_settings_accept_json_or_comma_separated_environment(monkeypatch) -> None:
    monkeypatch.setenv("OIDC_ALGORITHMS", "RS256")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://portal.example")
    monkeypatch.setenv("ALLOWED_HOSTS", '["portal.example","internal.example"]')

    settings = Settings(_env_file=None)

    assert settings.oidc_algorithms == ["RS256"]
    assert settings.allowed_origins == ["https://portal.example"]
    assert settings.allowed_hosts == ["portal.example", "internal.example"]
