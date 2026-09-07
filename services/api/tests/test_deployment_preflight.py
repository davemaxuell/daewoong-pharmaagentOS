from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/deployment-preflight.py"
SPEC = importlib.util.spec_from_file_location("deployment_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def manifest() -> list[dict]:
    return [
        {
            "kind": "ConfigMap",
            "metadata": {"name": "runtime"},
            "data": {
                "APP_ENV": "production",
                "DEV_AUTH_ENABLED": "false",
                "AUTO_CREATE_SCHEMA": "false",
                "ALLOWED_HOSTS": "api.internal",
                "AUTH_URL": "https://portal.example.com",
                "AUTH_ADMISSION_MODE": "restricted",
                "AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON": '{"google:123":["viewer"]}',
            },
        },
        {
            "kind": "Deployment",
            "metadata": {"name": "api"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "api",
                                "image": "registry.example/api@sha256:" + "a" * 64,
                                "envFrom": [{"configMapRef": {"name": "runtime"}}],
                            }
                        ],
                    }
                }
            },
        },
        {
            "kind": "NetworkPolicy",
            "spec": {
                "egress": [
                    {
                        "ports": [{"port": 5432}],
                        "to": [{"ipBlock": {"cidr": "10.0.1.3/32"}}],
                    }
                ]
            },
        },
    ]


def test_configured_manifest_passes_static_checks() -> None:
    assert preflight.inspect_documents(manifest()) == []


@pytest.mark.parametrize("documents", [[], ["invalid"], [{}], [{"kind": "Namespace"}]])
def test_empty_or_non_workload_input_cannot_pass(documents) -> None:
    assert preflight.inspect_documents(documents)


@pytest.mark.parametrize(
    "peers",
    [
        [],
        [{}],
        [{"ipBlock": {"cidr": "0.0.0.0/0"}}],
        [{"ipBlock": {"cidr": "::/0"}}],
        [{"namespaceSelector": {}}],
    ],
)
def test_database_egress_must_name_a_restricted_destination(peers) -> None:
    documents = manifest()
    documents[2]["spec"]["egress"][0]["to"] = peers
    assert any("restricted PostgreSQL" in error for error in preflight.inspect_documents(documents))


def test_missing_network_policies_cannot_pass() -> None:
    assert preflight.inspect_documents(manifest()[:2])


def test_inline_environment_override_cannot_bypass_production_validation() -> None:
    documents = manifest()
    container = documents[1]["spec"]["template"]["spec"]["containers"][0]
    container["env"] = [
        {"name": "DEV_AUTH_ENABLED", "value": "true"},
        {"name": "ALLOWED_HOSTS", "value": "*"},
    ]
    errors = preflight.inspect_documents(documents)
    assert any("DEV_AUTH_ENABLED=false" in error for error in errors)
    assert any("ALLOWED_HOSTS" in error for error in errors)


def test_init_containers_are_also_required_to_pin_images() -> None:
    documents = manifest()
    pod = documents[1]["spec"]["template"]["spec"]
    pod["initContainers"] = [{"name": "migration", "image": "registry.example/api:latest"}]
    assert any("migration by digest" in error for error in preflight.inspect_documents(documents))


def test_restricted_admission_requires_an_account_directory() -> None:
    documents = manifest()
    documents[0]["data"]["AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON"] = "{}"
    assert any("admitted subjects" in error for error in preflight.inspect_documents(documents))


def test_configmap_key_references_are_validated_after_resolution() -> None:
    documents = manifest()
    documents[0]["data"]["unsafe-dev-auth"] = "true"
    documents[1]["spec"]["template"]["spec"]["containers"][0]["env"] = [
        {
            "name": "DEV_AUTH_ENABLED",
            "valueFrom": {
                "configMapKeyRef": {
                    "name": "runtime",
                    "key": "unsafe-dev-auth",
                }
            },
        }
    ]
    assert any(
        "DEV_AUTH_ENABLED=false" in error for error in preflight.inspect_documents(documents)
    )


def test_configmap_resolution_is_namespace_scoped() -> None:
    documents = manifest()
    documents[0]["metadata"]["namespace"] = "other"
    assert any("referenced ConfigMap" in error for error in preflight.inspect_documents(documents))


def test_inspection_does_not_modify_the_manifest() -> None:
    documents = manifest()
    original = copy.deepcopy(documents)
    preflight.inspect_documents(documents)
    assert documents == original
