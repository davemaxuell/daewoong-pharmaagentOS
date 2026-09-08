"""Exercise real PostgreSQL locks; SQLite cannot qualify concurrent workers."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.database import Database
from app.models import ResearchRun
from app.research.schemas import CreateResearch
from app.research.service import control_run, create_run
from app.research.worker import LeaseLost, claim, mutate

pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_OS_POSTGRES_TEST") != "1",
    reason="requires isolated PostgreSQL migration CI service",
)


@pytest.mark.asyncio
async def test_duplicate_admission_single_claim_and_stop_fence():
    database = Database(os.environ["DATABASE_URL"])
    owner = "research-pg-" + uuid4().hex
    payload = CreateResearch(
        objective="Compare FDA validation findings", language="en", client_request_id=uuid4()
    )

    async def admit():
        async with database.session_factory() as session:
            return await create_run(session, owner, payload)

    try:
        first, second = await asyncio.gather(admit(), admit())
        assert first.id == second.id
        claims = await asyncio.gather(*(claim(database) for _ in range(4)))
        claimed = [run for run in claims if run is not None]
        assert len(claimed) == 1
        run = claimed[0]
        assert run.id == first.id
        async with database.session_factory() as session:
            await control_run(session, run.id, owner, "stop")
        with pytest.raises(LeaseLost):
            await mutate(
                database,
                run.id,
                run.lease_id,
                lambda _session, current: setattr(current, "status", "completed"),
            )
        async with database.session_factory() as session:
            retained = await session.get(ResearchRun, run.id)
            assert retained.status == "stopped"
            assert retained.result is None
    finally:
        async with database.session_factory() as session:
            await session.execute(delete(ResearchRun).where(ResearchRun.owner_id == owner))
            await session.commit()
        await database.dispose()
