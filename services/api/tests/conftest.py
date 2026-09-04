from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.seed import seed_demo

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
FDA_FIXTURES = WORKSPACE_ROOT / "tests" / "fixtures" / "fda"


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FDA_FIXTURES


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        object_store_path=tmp_path / "objects",
        fda_request_delay_seconds=0,
        fda_robots_cache_seconds=3_600,
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        llm_provider="none",
        gemini_api_key=None,
    )


async def _seed_database(settings: Settings, fixture_dir: Path) -> None:
    database = Database(settings.database_url)
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await seed_demo(session, settings, fixture_dir)
    finally:
        await database.dispose()


@pytest.fixture(scope="module")
def client(tmp_path_factory, fixture_dir: Path) -> Iterator[TestClient]:
    root = tmp_path_factory.mktemp("api-client")
    client_settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(root / 'test.db').as_posix()}",
        object_store_path=root / "objects",
        fda_request_delay_seconds=0,
        fda_robots_cache_seconds=3_600,
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        llm_provider="none",
        gemini_api_key=None,
    )
    asyncio.run(_seed_database(client_settings, fixture_dir))
    app = create_app(client_settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def viewer_headers() -> dict[str, str]:
    return {"X-Dev-User": "local.user", "X-Dev-Roles": "viewer"}


@pytest.fixture(scope="session")
def reviewer_headers() -> dict[str, str]:
    return {"X-Dev-User": "reviewer.user", "X-Dev-Roles": "reviewer"}


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    return {"X-Dev-User": "admin.user", "X-Dev-Roles": "admin"}
