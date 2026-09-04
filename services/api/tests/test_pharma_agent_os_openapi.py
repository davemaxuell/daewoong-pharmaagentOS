from __future__ import annotations

from fastapi.testclient import TestClient


def test_runtime_openapi_covers_the_complete_pharma_agent_os_surface(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    paths = set(document["paths"])

    required_paths = {
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/plans",
        "/api/v1/cases/{case_id}/plans/{version}/approve",
        "/api/v1/approvals",
        "/api/v1/approvals/{approval_id}",
        "/api/v1/cases/{case_id}/runs",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/pause",
        "/api/v1/runs/{run_id}/resume",
        "/api/v1/runs/{run_id}/cancel",
        "/api/v1/runs/{run_id}/events",
        "/api/v1/cases/{case_id}/knowledge/search",
        "/api/v1/cases/{case_id}/impact/generate",
        "/api/v1/cases/{case_id}/verification",
        "/api/v1/cases/{case_id}/artifacts/compose",
        "/api/v1/workflow-templates",
        "/api/v1/eval-suites",
        "/api/v1/eval-runs",
        "/api/v1/eval-runs/{run_id}/approve-release",
        "/api/v1/control-tower/summary",
        "/api/v1/control-tower/inventory",
        "/api/v1/control-tower/controls/global",
        "/api/v1/control-tower/controls/agents/{agent_version_id}",
        "/api/v1/cases/{case_id}/integration-drafts",
        "/api/v1/integration-drafts/{draft_id}/review",
        "/api/v1/cases/{case_id}/document-metadata/{asset_version_id}",
        "/api/v1/a2a/tasks",
    }
    assert not required_paths - paths


def test_runtime_openapi_declares_hash_and_no_delivery_integration_fields(
    client: TestClient,
) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    draft = schemas["IntegrationDraftResponse"]["properties"]

    assert draft["content_sha256"]["type"] == "string"
    assert draft["external_delivery_allowed"]["const"] is False
    assert schemas["DraftCreateRequest"]["additionalProperties"] is False
    assert schemas["A2ATaskRequest"]["additionalProperties"] is False
