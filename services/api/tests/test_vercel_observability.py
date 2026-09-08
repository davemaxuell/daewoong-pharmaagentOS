import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.observability import VercelRequestLogMiddleware


def test_platform_logging_requires_real_vercel_configuration():
    with pytest.raises(ValidationError, match="managed Vercel runtime metadata"):
        Settings(_env_file=None, telemetry_backend="vercel_logs")


def test_request_logs_exclude_private_content_and_use_route_templates(capsys):
    app = FastAPI()
    app.add_middleware(VercelRequestLogMiddleware, service_name="test-api")

    @app.post("/documents/{document_id}")
    async def document(document_id: str, request: Request):
        return {"content": await request.json()}

    client = TestClient(app)
    response = client.post(
        "/documents/private-document?secret=private-query",
        headers={"authorization": "Bearer private-key"},
        json={"data": "private-body"},
    )
    assert response.status_code == 200
    output = capsys.readouterr().out
    assert "private-" not in output
    event = json.loads(output)
    assert event["route"] == "/documents/{document_id}"
    assert event["status"] == 200 and event["completed"] is True


def test_failed_request_logs_metadata_without_exception_contents(capsys):
    app = FastAPI()
    app.add_middleware(VercelRequestLogMiddleware, service_name="test-api")

    @app.get("/failure")
    async def failure():
        raise RuntimeError("private-exception-content")

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/failure").status_code == 500
    output = capsys.readouterr().out
    assert "private-exception-content" not in output
    event = json.loads(output)
    assert event["status"] == 500 and event["completed"] is False
