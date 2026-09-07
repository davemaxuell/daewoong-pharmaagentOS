from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Protocol

import boto3

from app.config import Settings


@dataclass(frozen=True)
class SecretRef:
    name: str


class SecretProvider(Protocol):
    async def resolve(self, ref: SecretRef) -> str: ...


class EnvironmentSecretProvider:
    """Local/test provider. Values are never retained outside the caller."""

    async def resolve(self, ref: SecretRef) -> str:
        value = os.environ.get(ref.name)
        if not value:
            raise LookupError(f"Required secret reference is unavailable: {ref.name}")
        return value


class AwsSecretsManagerProvider:
    """Workload-identity AWS Secrets Manager adapter with no static credential inputs."""

    def __init__(self, *, region: str, prefix: str) -> None:
        self._client = boto3.client("secretsmanager", region_name=region)
        self._prefix = prefix

    async def resolve(self, ref: SecretRef) -> str:
        response = await asyncio.to_thread(
            self._client.get_secret_value,
            SecretId=f"{self._prefix}{ref.name}",
        )
        value = response.get("SecretString")
        if not value:
            raise LookupError(f"Required secret reference is unavailable: {ref.name}")
        return str(value)


class VercelSecretProvider(EnvironmentSecretProvider):
    """Vercel injects deployment-scoped Secret values into the process environment.

    Configure these as Secret values in Vercel, separately for Preview/Production.
    Metadata checks prevent accidental local selection; they are not a remote
    attestation or proof of the dashboard's variable visibility setting.
    Consumers already receive the same injected values through Settings.
    """


def build_secret_provider(settings: Settings) -> SecretProvider:
    if settings.secret_provider == "vercel":
        return VercelSecretProvider()
    if settings.secret_provider == "aws":
        assert settings.secrets_aws_region is not None
        return AwsSecretsManagerProvider(
            region=settings.secrets_aws_region,
            prefix=settings.secrets_aws_prefix,
        )
    return EnvironmentSecretProvider()
