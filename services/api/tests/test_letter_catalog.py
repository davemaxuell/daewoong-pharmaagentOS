from fastapi.testclient import TestClient

from app.routes import core


def test_catalog_preserves_scope_and_existing_metadata(
    client: TestClient, viewer_headers: dict[str, str]
) -> None:
    assert client.get("/api/v1/letters/catalog").status_code == 401
    expected = client.get("/api/v1/letters?limit=100", headers=viewer_headers).json()
    actual = client.get("/api/v1/letters/catalog", headers=viewer_headers)
    assert actual.status_code == 200
    assert actual.json() == expected
    assert all(item["current_in_scope"] for item in actual.json()["items"])
    assert all(item["scope_status"] == "IN_SCOPE_DRUGS" for item in actual.json()["items"])
    assert all("original_sections" not in item for item in actual.json()["items"])


def test_catalog_bounds_context_work_to_each_page(
    client: TestClient, viewer_headers: dict[str, str], monkeypatch
) -> None:
    context_sizes = []
    original = core._letter_context

    async def measured_context(session, letters):
        context_sizes.append(len(letters))
        return await original(session, letters)

    monkeypatch.setattr(core, "_letter_context", measured_context)
    first = client.get("/api/v1/letters/catalog?limit=2", headers=viewer_headers).json()
    assert first["has_more"]
    second = client.get(
        f"/api/v1/letters/catalog?limit=2&cursor={first['next_cursor']}", headers=viewer_headers
    ).json()
    assert not second["has_more"]
    assert context_sizes == [2, 2]
    assert len({item["id"] for item in first["items"] + second["items"]}) == 4
    for query, status in [("limit=1001", 422), ("limit=0", 422), ("cursor=invalid", 400)]:
        response = client.get(f"/api/v1/letters/catalog?{query}", headers=viewer_headers)
        assert response.status_code == status
