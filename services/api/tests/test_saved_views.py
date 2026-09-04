from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.models import Subscription
from app.routes.intelligence import _saved_view_alert_state


def test_saved_view_alert_readiness_is_truthful_for_each_cadence(settings: Settings) -> None:
    subscription = Subscription(
        owner_id="alert-state.user",
        name="Alert state",
        criteria={},
        frequency="immediate",
        channel="email",
        destination_id="alerts@example.com",
        active=True,
    )
    assert _saved_view_alert_state(subscription, settings) == "delivery_unavailable"

    smtp_settings = settings.model_copy(
        update={
            "smtp_enabled": True,
            "smtp_host": "smtp.example.test",
            "smtp_from_email": "sender@example.com",
        }
    )
    assert _saved_view_alert_state(subscription, smtp_settings) == "ready"

    subscription.frequency = "daily"
    assert _saved_view_alert_state(subscription, smtp_settings) == (
        "digest_scheduler_unavailable"
    )
    subscription.frequency = "weekly"
    assert _saved_view_alert_state(subscription, smtp_settings) == (
        "digest_scheduler_unavailable"
    )
    subscription.active = False
    assert _saved_view_alert_state(subscription, smtp_settings) == "off"


def test_saved_view_crud_persists_controlled_filters_for_owner(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    letters = client.get("/api/v1/letters?limit=100", headers=viewer_headers)
    assert letters.status_code == 200
    first_letter = letters.json()["items"][0]
    company = first_letter["company_name"]
    linked_document = "closeout" if first_letter["has_closeout"] else "open"

    created = client.post(
        "/api/v1/saved-views",
        headers=viewer_headers,
        json={
            "name": "Owner-persisted company watch",
            "description": "Restore the same company and open-lifecycle filters.",
            "criteria": {
                "query": company,
                "linked_document": linked_document,
            },
            "cadence": "off",
        },
    )
    assert created.status_code == 201
    body = created.json()
    saved_view_id = body["id"]
    assert body["criteria"] == {
        "query": company,
        "drug_subtype": None,
        "category": None,
        "country": None,
        "lifecycle_state": None,
        "review_state": None,
        "linked_document": linked_document,
        "posted_from": None,
        "posted_to": None,
    }
    assert body["active"] is False
    assert body["alert_state"] == "off"
    assert body["result_count"] >= 1
    assert body["owner_id"] == "local.user"
    assert body["open_url"].startswith("/drug-letters?")
    assert "q=" in body["open_url"]
    assert f"document={linked_document}" in body["open_url"]

    refreshed = client.get("/api/v1/saved-views?limit=100", headers=viewer_headers)
    assert refreshed.status_code == 200
    persisted = next(item for item in refreshed.json()["items"] if item["id"] == saved_view_id)
    assert persisted["description"] == "Restore the same company and open-lifecycle filters."
    assert persisted["criteria"]["query"] == company

    updated = client.patch(
        f"/api/v1/saved-views/{saved_view_id}",
        headers=viewer_headers,
        json={
            "description": "Updated and durable.",
            "criteria": {"country": "United States"},
            "cadence": "immediate",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated and durable."
    assert updated.json()["criteria"]["country"] == "United States"
    assert updated.json()["active"] is True
    assert updated.json()["frequency"] == "immediate"
    assert updated.json()["alert_state"] == "delivery_unavailable"

    other_headers = {"X-Dev-User": "other.user", "X-Dev-Roles": "viewer"}
    assert client.get("/api/v1/saved-views", headers=other_headers).json()["items"] == []
    assert (
        client.patch(
            f"/api/v1/saved-views/{saved_view_id}",
            headers=other_headers,
            json={"cadence": "off"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/saved-views/{saved_view_id}", headers=other_headers).status_code
        == 404
    )

    deleted = client.delete(f"/api/v1/saved-views/{saved_view_id}", headers=viewer_headers)
    assert deleted.status_code == 204
    remaining_ids = {
        item["id"]
        for item in client.get(
            "/api/v1/saved-views?limit=100", headers=viewer_headers
        ).json()["items"]
    }
    assert saved_view_id not in remaining_ids


def test_saved_view_rejects_invalid_ranges_and_duplicate_names(
    client: TestClient,
    viewer_headers: dict[str, str],
) -> None:
    invalid = client.post(
        "/api/v1/saved-views",
        headers=viewer_headers,
        json={
            "name": "Invalid date range",
            "criteria": {"posted_from": "2026-08-31", "posted_to": "2026-01-01"},
            "cadence": "off",
        },
    )
    assert invalid.status_code == 422

    payload = {
        "name": "Unique saved-view name",
        "criteria": {"category": "Quality Unit / QA Oversight"},
        "cadence": "weekly",
    }
    first = client.post("/api/v1/saved-views", headers=viewer_headers, json=payload)
    duplicate = client.post("/api/v1/saved-views", headers=viewer_headers, json=payload)
    assert first.status_code == 201
    assert first.json()["alert_state"] == "digest_scheduler_unavailable"
    assert duplicate.status_code == 409
    assert client.delete(
        f"/api/v1/saved-views/{first.json()['id']}", headers=viewer_headers
    ).status_code == 204
