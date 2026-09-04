from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import InvalidTokenError, PyJWKClient

from app.config import Settings

ROLE_ALIASES = {
    "viewer": "viewer",
    "analyst": "analyst",
    "regulatory_analyst": "analyst",
    "reviewer": "reviewer",
    "qa_reviewer": "reviewer",
    "domain_sme": "domain_sme",
    "sme": "domain_sme",
    "agent_developer": "agent_developer",
    "platform_admin": "platform_admin",
    "platform_administrator": "platform_admin",
    "system_owner": "system_owner",
    "admin": "admin",
    "system_administrator": "admin",
    "auditor": "auditor",
    "security_auditor": "auditor",
    "service": "service",
    "service_account": "service",
}

TRUSTED_ACCOUNT_SUBJECT = re.compile(r"^(?:google|naver):[^:]{1,255}$")
TRUSTED_SERVICE_SUBJECT = re.compile(r"^svc:[a-z0-9][a-z0-9._-]{1,120}$")


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    actor_type: str = "user"
    claims: dict[str, Any] | None = None

    def has_any(self, allowed: set[str] | frozenset[str]) -> bool:
        return bool(self.roles.intersection(allowed))


def _unauthorized(detail: str = "A valid corporate identity is required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _roles_from_value(value: object) -> set[str]:
    if isinstance(value, str):
        raw = [part.strip() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        raw = [str(part).strip() for part in value]
    else:
        raw = []
    return {ROLE_ALIASES[item.casefold()] for item in raw if item.casefold() in ROLE_ALIASES}


async def _decode_bearer(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise _unauthorized("Bearer token header is invalid") from exc
    algorithm = str(header.get("alg", ""))
    if algorithm not in settings.oidc_algorithms or algorithm.casefold() == "none":
        raise _unauthorized("Bearer token algorithm is not allowed")

    key: Any
    if algorithm.startswith("HS"):
        if not settings.oidc_hs256_secret:
            raise _unauthorized("Bearer token verification is not configured")
        key = settings.oidc_hs256_secret.get_secret_value()
    elif settings.oidc_public_key:
        key = settings.oidc_public_key
    elif settings.oidc_jwks_url:
        client = PyJWKClient(settings.oidc_jwks_url, cache_keys=True)
        try:
            signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        except Exception as exc:
            raise _unauthorized("Bearer token signing key could not be resolved") from exc
        key = signing_key.key
    else:
        raise _unauthorized("Bearer token verification is not configured")

    required_claims = ["exp", "sub"]
    if settings.app_env == "production":
        required_claims.extend(["iat", "nbf", "jti"])
    options = {"require": required_claims}
    if settings.oidc_issuer:
        options["require"].append("iss")
    if settings.oidc_audience:
        options["require"].append("aud")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=settings.oidc_algorithms,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options=options,
        )
    except InvalidTokenError as exc:
        raise _unauthorized("Bearer token is invalid or expired") from exc
    if settings.app_env == "production":
        token_use = claims.get("token_use")
        subject = str(claims.get("sub", ""))
        roles = _roles_from_value(claims.get(settings.oidc_role_claim))
        if token_use == "api_session":
            if not TRUSTED_ACCOUNT_SUBJECT.fullmatch(subject):
                raise _unauthorized("Bearer token subject is not a trusted account identity")
            maximum_lifetime = 120
        elif token_use == "service_access":
            if not TRUSTED_SERVICE_SUBJECT.fullmatch(subject) or roles != {"service"}:
                raise _unauthorized("Bearer token service identity is invalid")
            maximum_lifetime = 300
        else:
            raise _unauthorized("Bearer token purpose is invalid")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(issued_at, (int, float)) or not isinstance(expires_at, (int, float)):
            raise _unauthorized("Bearer token lifetime is invalid")
        if expires_at <= issued_at or expires_at - issued_at > maximum_lifetime:
            raise _unauthorized("Bearer token lifetime exceeds the application-session limit")
    return claims


async def current_principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    authorization = request.headers.get("authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise _unauthorized("Authorization must use a Bearer token")
        claims = await _decode_bearer(token, settings)
        subject = str(claims.get("sub", "")).strip()
        if not subject:
            raise _unauthorized("Bearer token subject is missing")
        roles = _roles_from_value(claims.get(settings.oidc_role_claim))
        groups = claims.get("groups", [])
        if isinstance(groups, str):
            groups = [groups]
        if isinstance(groups, list):
            roles.update(
                ROLE_ALIASES[mapped.casefold()]
                for group in groups
                if (mapped := settings.oidc_group_role_map.get(str(group)))
                and mapped.casefold() in ROLE_ALIASES
            )
        if not roles:
            raise HTTPException(status_code=403, detail="No recognized application role")
        actor_type = "service" if claims.get("token_use") == "service_access" else "user"
        # Group mappings are another source of authority. Check the final role
        # set, not just the signed roles claim inspected by _decode_bearer.
        if settings.app_env == "production":
            if actor_type == "service" and roles != {"service"}:
                raise _unauthorized(
                    "Bearer token service identity has incompatible effective roles"
                )
            if actor_type == "user" and "service" in roles:
                raise _unauthorized("Human identities cannot receive the service role")
        return Principal(subject, frozenset(roles), actor_type=actor_type, claims=claims)

    dev_user = request.headers.get("x-dev-user", "").strip()
    dev_roles = request.headers.get("x-dev-roles", "").strip()
    if settings.dev_auth_enabled and settings.app_env != "production" and dev_user:
        roles = _roles_from_value(dev_roles or "viewer")
        if not roles:
            raise HTTPException(status_code=403, detail="No recognized development role")
        return Principal(dev_user[:255], frozenset(roles), claims={"development": True})
    raise _unauthorized()


def require_roles(*allowed: str):
    normalized = {ROLE_ALIASES.get(role.casefold(), role.casefold()) for role in allowed}

    async def dependency(
        principal: Principal = Depends(current_principal),
    ) -> Principal:
        if not principal.has_any(normalized):
            raise HTTPException(status_code=403, detail="Application role is not authorized")
        return principal

    return dependency


view_principal = require_roles(
    "viewer",
    "analyst",
    "reviewer",
    "domain_sme",
    "system_owner",
    "admin",
    "auditor",
)
rag_principal = require_roles(
    "viewer", "analyst", "reviewer", "domain_sme", "system_owner", "admin"
)
reviewer_principal = require_roles("reviewer")
admin_principal = require_roles("admin")
admin_auditor_principal = require_roles("admin", "auditor")
agent_developer_principal = require_roles("agent_developer")
platform_admin_principal = require_roles("platform_admin")
system_owner_principal = require_roles("system_owner")
