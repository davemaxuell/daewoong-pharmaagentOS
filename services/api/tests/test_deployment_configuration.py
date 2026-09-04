"""Check the shipped workload wiring with synthetic secrets, without a cluster."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BASE = Path(__file__).resolve().parents[3] / "infra/deployment/kubernetes/base"
CONFIG = yaml.safe_load((BASE / "configmap.yaml").read_text(encoding="utf-8"))["data"]
WORKLOADS = {
    doc["metadata"]["name"]: doc["spec"]["template"]["spec"]
    for name in ("workloads.yaml", "agent-platform-workloads.yaml")
    for doc in yaml.safe_load_all((BASE / name).read_text(encoding="utf-8"))
}
API_WORKLOADS = ["fda-api", "fda-worker", "pharma-mcp-gateway", "pharma-orchestrator"]
SYNTHETIC_VALUES = {
    "database-url": "postgresql+asyncpg://fixture:fixture@127.0.0.1/fixture",
    "api-session-public-key": "synthetic-public-key-not-for-token-verification",
    "service-token-public-key": "synthetic-service-public-key-not-for-token-verification",
    "gemini-api-key": "synthetic-unusable-fixture",
    "object-store-endpoint": "https://storage.example.invalid",
    "object-store-bucket": "fixture-evidence",
    "object-store-region": "ap-northeast-2",
    "object-store-access-key-id": "synthetic-unusable-id",
    "object-store-secret-access-key": "synthetic-unusable-value",
}


def _environment(name: str) -> dict[str, str]:
    container = WORKLOADS[name]["containers"][0]
    assert container["envFrom"] == [{"configMapRef": {"name": "fda-runtime-config"}}]
    environment = dict(CONFIG)
    for entry in container["env"]:
        environment[entry["name"]] = (
            str(entry["value"])
            if "value" in entry
            else SYNTHETIC_VALUES[entry["valueFrom"]["secretKeyRef"]["key"]]
        )
    return environment


def _settings(name: str) -> Settings:
    with patch.dict(os.environ, _environment(name), clear=True):
        return Settings(_env_file=None)


@pytest.mark.parametrize("name", API_WORKLOADS)
def test_each_backend_workload_has_valid_production_settings(name: str) -> None:
    settings = _settings(name)
    assert settings.app_env == "production"
    assert settings.dev_auth_enabled is False
    assert settings.auto_create_schema is False
    assert settings.oidc_public_key


@pytest.mark.parametrize("name", ["pharma-mcp-gateway", "pharma-orchestrator"])
def test_non_model_workloads_do_not_require_model_secrets(name: str) -> None:
    settings = _settings(name)
    assert settings.llm_provider == "none"
    assert not settings.embedding_enabled
    assert "GEMINI_API_KEY" not in _environment(name)


@pytest.mark.parametrize("name", ["fda-api", "fda-worker"])
def test_evidence_workloads_use_explicit_remote_storage(name: str) -> None:
    assert _settings(name).object_store_backend == "s3"
    for entry in WORKLOADS[name]["containers"][0]["env"]:
        if entry["name"].startswith("OBJECT_STORE_S3_"):
            assert entry["valueFrom"]["secretKeyRef"]["name"] == f"{name}-runtime"


@pytest.mark.parametrize("name", API_WORKLOADS)
def test_temporal_clients_have_mounted_certificate_paths(name: str) -> None:
    settings = _settings(name)
    assert settings.temporal_enabled == (name in {"fda-api", "pharma-orchestrator"})
    if not settings.temporal_enabled:
        return
    pod = WORKLOADS[name]
    mount = next(
        item
        for item in pod["containers"][0]["volumeMounts"]
        if item["mountPath"] == "/var/run/secrets/temporal"
    )
    volume = next(item for item in pod["volumes"] if item["name"] == mount["name"])
    assert mount["readOnly"] is True
    assert volume["secret"]["secretName"] == "pharma-temporal-mtls"
    for path in (
        settings.temporal_tls_ca_path,
        settings.temporal_tls_cert_path,
        settings.temporal_tls_key_path,
    ):
        assert path is not None
        assert PurePosixPath(str(path).replace("\\", "/")).is_relative_to(mount["mountPath"])


def test_declared_api_probes_pass_host_validation(tmp_path, monkeypatch) -> None:
    # Test the real application middleware. External service factories alone are
    # replaced; the database is an isolated, explicitly prepared local fixture.
    settings = _settings("fda-api").model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'probe.db').as_posix()}",
            "object_store_backend": "local",
            "object_store_path": tmp_path / "objects",
            "llm_provider": "none",
            "embedding_enabled": False,
        }
    )
    monkeypatch.setattr("app.main.build_secret_provider", lambda _: object())
    monkeypatch.setattr("app.main.configure_telemetry", lambda *_: None)
    app = create_app(settings)
    asyncio.run(app.state.database.create_schema())
    container = WORKLOADS["fda-api"]["containers"][0]
    with TestClient(app) as client:
        for name in ("startupProbe", "livenessProbe", "readinessProbe"):
            probe = container[name]["httpGet"]
            assert "host" not in probe  # Connect to the Pod, not the Service.
            headers = {item["name"]: item["value"] for item in probe["httpHeaders"]}
            assert headers["Host"] in json.loads(CONFIG["ALLOWED_HOSTS"])
            assert client.get(probe["path"], headers=headers).status_code == 200
        assert client.get("/health/live", headers={"Host": "untrusted.invalid"}).status_code == 400
        assert client.get("/api/v1/cases", headers={"Host": "fda-api"}).status_code == 401
