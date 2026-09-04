from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.agent_platform.temporal.activities import CaseActivities
from app.agent_platform.temporal.client import temporal_tls
from app.agent_platform.temporal.workflow import PharmaCaseOuterWorkflow
from app.config import get_settings
from app.database import Database


async def run_temporal_worker() -> None:
    settings = get_settings()
    if not settings.temporal_enabled:
        raise RuntimeError("TEMPORAL_ENABLED must be true for the Temporal worker")
    database = Database(settings.database_url)
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        tls=temporal_tls(settings),
        identity="pharma-case-orchestrator",
    )
    activities = CaseActivities(database)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[PharmaCaseOuterWorkflow],
        activities=[activities.advance_case_run_activity],
    )
    try:
        await worker.run()
    finally:
        await database.dispose()


def main() -> None:
    asyncio.run(run_temporal_worker())


if __name__ == "__main__":
    main()
