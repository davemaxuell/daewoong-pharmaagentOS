from __future__ import annotations

from typing import Any

from sqlalchemy import select
from temporalio import activity

from app.agent_platform.runtime.service import advance_case_run
from app.cases.hashing import canonical_sha256
from app.database import Database
from app.models import CaseRun, DurableActivity, utcnow
from app.security.auth import Principal


class CaseActivities:
    def __init__(self, database: Database) -> None:
        self._database = database

    @activity.defn(name="advance_case_run_activity")
    async def advance_case_run_activity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await execute_advance_activity(self._database, payload)


async def execute_advance_activity(
    database: Database,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute exactly once per workflow/activity key, replaying committed results on retry."""

    run_id = str(payload["run_id"])
    workflow_id = str(payload["workflow_id"])
    activity_key = str(payload["activity_key"])
    input_sha256 = canonical_sha256(payload)
    captured_error: Exception | None = None
    response: dict[str, Any] | None = None
    async with database.session_factory() as session:
        record = await session.scalar(
            select(DurableActivity)
            .where(
                DurableActivity.temporal_workflow_id == workflow_id,
                DurableActivity.activity_key == activity_key,
            )
            .with_for_update()
        )
        if record and record.input_sha256 != input_sha256:
            raise RuntimeError("Durable activity idempotency payload conflict")
        if record and record.status == "SUCCEEDED":
            return dict(record.result or {})
        if record:
            record.status = "RUNNING"
            record.attempts += 1
            record.last_error = None
        else:
            record = DurableActivity(
                temporal_workflow_id=workflow_id,
                case_run_id=run_id,
                activity_key=activity_key,
                input_sha256=input_sha256,
                status="RUNNING",
            )
            session.add(record)
            await session.flush()
        try:
            # Roll back partial step writes before recording a retryable failure.
            # The journal and successful business writes still commit atomically.
            async with session.begin_nested():
                metrics = await advance_case_run(
                    session,
                    run_id=run_id,
                    request_id=f"temporal:{workflow_id}:{activity_key}",
                    actor=Principal(
                        subject="svc:pharma-orchestrator",
                        roles=frozenset({"service"}),
                        actor_type="service",
                    ),
                )
            run = await session.get(CaseRun, run_id)
            if run is None:
                raise RuntimeError("Case run disappeared during durable activity")
            response = {"run_id": run.id, "status": run.status, "metrics": metrics}
            record.status = "SUCCEEDED"
            record.result = response
            record.result_sha256 = canonical_sha256(response)
            record.completed_at = utcnow()
        except Exception as exc:  # persisted before Temporal observes the retryable failure
            captured_error = exc
            record.status = "FAILED"
            record.last_error = type(exc).__name__[:120]
            record.completed_at = utcnow()
        await session.commit()
    if captured_error:
        raise RuntimeError("Durable case activity failed") from captured_error
    assert response is not None
    return response
