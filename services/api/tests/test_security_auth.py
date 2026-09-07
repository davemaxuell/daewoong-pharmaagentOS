from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Request

from app.config import Settings
from app.security.auth import _decode_bearer, _roles_from_value, current_principal, require_roles


def test_public_key_environment_newlines_are_normalized() -> None:
    settings = Settings(app_env="test", oidc_public_key="line-one\\nline-two")
    assert settings.oidc_public_key == "line-one\nline-two"


def test_agent_platform_roles_are_normalized_without_collapsing_separation_of_duties() -> None:
    roles = _roles_from_value(
        ["regulatory_analyst", "qa_reviewer", "sme", "agent_developer", "platform_administrator"]
    )

    assert roles == {
        "analyst",
        "reviewer",
        "domain_sme",
        "agent_developer",
        "platform_admin",
    }
    assert "admin" not in roles


def test_system_owner_is_a_distinct_agent_platform_role() -> None:
    assert _roles_from_value("system_owner") == {"system_owner"}


def _production_settings(public_key: str) -> Settings:
    return Settings(
        app_env="production",
        database_url="postgresql+asyncpg://fixture:fixture@db.internal/fixture",
        auto_create_schema=False,
        dev_auth_enabled=False,
        allowed_origins=["https://fda.example"],
        allowed_hosts=["fda.example"],
        oidc_issuer="daewoong-fda-web",
        oidc_audience="daewoong-fda-api",
        oidc_public_key=public_key,
        oidc_algorithms=["RS256"],
        otel_exporter_otlp_endpoint="https://otel.example/v1/traces",
        secret_provider="aws",
        secrets_aws_region="ap-northeast-2",
    )


@pytest.fixture
def signing_material() -> tuple[object, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_key, public_key


def _token(private_key: object, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": "google:immutable-subject",
        "iss": "daewoong-fda-web",
        "aud": "daewoong-fda-api",
        "iat": now,
        "nbf": now - timedelta(seconds=5),
        "exp": now + timedelta(seconds=90),
        "jti": "test-session-id",
        "token_use": "api_session",
        "roles": ["viewer"],
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def _request(token: str, settings: Settings) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        }
    )


@pytest.mark.parametrize("mapped_role", ["admin", "system_owner", "reviewer", "viewer"])
@pytest.mark.parametrize("groups", [["operators"], "operators"])
async def test_service_identity_rejects_human_roles_from_group_mapping(
    signing_material,
    mapped_role,
    groups,
) -> None:
    private_key, public_key = signing_material
    settings = _production_settings(public_key).model_copy(
        update={"oidc_group_role_map": {"operators": mapped_role}}
    )
    token = _token(
        private_key,
        sub="svc:orchestrator",
        token_use="service_access",
        roles=["service"],
        groups=groups,
    )
    with pytest.raises(HTTPException) as error:
        await current_principal(_request(token, settings))
    assert error.value.status_code == 401
    assert "effective roles" in error.value.detail


@pytest.mark.parametrize("mapped_role", ["service", "service_account"])
async def test_service_only_group_mapping_remains_valid(signing_material, mapped_role) -> None:
    private_key, public_key = signing_material
    settings = _production_settings(public_key).model_copy(
        update={"oidc_group_role_map": {"machines": mapped_role}}
    )
    token = _token(
        private_key,
        sub="svc:orchestrator",
        token_use="service_access",
        roles=["service"],
        groups=["machines", "unknown"],
    )
    principal = await current_principal(_request(token, settings))
    assert principal.actor_type == "service"
    assert principal.roles == frozenset({"service"})
    assert await require_roles("service")(principal) == principal
    with pytest.raises(HTTPException) as error:
        await require_roles("admin")(principal)
    assert error.value.status_code == 403


@pytest.mark.parametrize("roles", [["viewer"], ["service"]])
async def test_human_identity_cannot_gain_service_role(signing_material, roles) -> None:
    private_key, public_key = signing_material
    settings = _production_settings(public_key).model_copy(
        update={"oidc_group_role_map": {"machines": "service"}}
    )
    token = _token(private_key, roles=roles, groups=["machines"])
    with pytest.raises(HTTPException) as error:
        await current_principal(_request(token, settings))
    assert error.value.status_code == 401
    assert "Human identities" in error.value.detail


async def test_human_group_mapping_remains_valid(signing_material) -> None:
    private_key, public_key = signing_material
    settings = _production_settings(public_key).model_copy(
        update={"oidc_group_role_map": {"reviewers": "qa_reviewer"}}
    )
    principal = await current_principal(
        _request(
            _token(private_key, groups=["reviewers"]),
            settings,
        )
    )
    assert principal.actor_type == "user"
    assert principal.roles == frozenset({"viewer", "reviewer"})


async def test_production_accepts_only_the_short_lived_application_assertion(
    signing_material: tuple[object, str],
) -> None:
    private_key, public_key = signing_material
    claims = await _decode_bearer(
        _token(private_key),
        _production_settings(public_key),
    )
    assert claims["sub"] == "google:immutable-subject"
    assert claims["token_use"] == "api_session"


async def test_production_accepts_naver_application_identity(
    signing_material: tuple[object, str],
) -> None:
    private_key, public_key = signing_material
    claims = await _decode_bearer(
        _token(private_key, sub="naver:application-scoped-subject"),
        _production_settings(public_key),
    )
    assert claims["sub"] == "naver:application-scoped-subject"


async def test_production_accepts_short_lived_service_identity_only_with_service_role(
    signing_material: tuple[object, str],
) -> None:
    private_key, public_key = signing_material
    claims = await _decode_bearer(
        _token(
            private_key,
            sub="svc:pharma-orchestrator",
            token_use="service_access",
            roles=["service"],
        ),
        _production_settings(public_key),
    )
    assert claims["sub"] == "svc:pharma-orchestrator"


async def test_production_rejects_privileged_human_roles_on_service_identity(
    signing_material: tuple[object, str],
) -> None:
    private_key, public_key = signing_material
    with pytest.raises(HTTPException, match="service identity"):
        await _decode_bearer(
            _token(
                private_key,
                sub="svc:pharma-orchestrator",
                token_use="service_access",
                roles=["service", "system_owner"],
            ),
            _production_settings(public_key),
        )


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"token_use": "id_token"}, "purpose"),
        ({"sub": "email@example.com"}, "trusted account identity"),
        ({"sub": "naver:invalid:subject"}, "trusted account identity"),
    ],
)
async def test_production_rejects_wrong_token_purpose_or_subject(
    signing_material: tuple[object, str],
    overrides: dict[str, object],
    detail: str,
) -> None:
    private_key, public_key = signing_material
    with pytest.raises(HTTPException) as exc_info:
        await _decode_bearer(
            _token(private_key, **overrides),
            _production_settings(public_key),
        )
    assert exc_info.value.status_code == 401
    assert detail in str(exc_info.value.detail)


async def test_production_rejects_long_lived_application_assertion(
    signing_material: tuple[object, str],
) -> None:
    private_key, public_key = signing_material
    now = datetime.now(UTC)
    with pytest.raises(HTTPException) as exc_info:
        await _decode_bearer(
            _token(private_key, iat=now, exp=now + timedelta(minutes=10)),
            _production_settings(public_key),
        )
    assert exc_info.value.status_code == 401
    assert "lifetime" in str(exc_info.value.detail)
