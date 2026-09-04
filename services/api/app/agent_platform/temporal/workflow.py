from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TERMINAL_STATUSES = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}


@workflow.defn(name="PharmaCaseOuterWorkflow")
class PharmaCaseOuterWorkflow:
    """Durable outer loop; LangGraph remains the bounded in-step decision engine."""

    def __init__(self) -> None:
        self._wake_revision = 0
        self._cancel_requested = False
        self._state: dict[str, Any] = {"status": "PENDING", "cycle": 0}

    @workflow.signal
    def wake(self) -> None:
        self._wake_revision += 1

    @workflow.signal
    def cancel(self) -> None:
        self._cancel_requested = True
        self._wake_revision += 1

    @workflow.query
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload["run_id"])
        while not self._cancel_requested:
            cycle = int(self._state["cycle"]) + 1
            result = await workflow.execute_activity(
                "advance_case_run_activity",
                {
                    "run_id": run_id,
                    "workflow_id": workflow.info().workflow_id,
                    "activity_key": f"advance:{cycle}",
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=5,
                ),
            )
            self._state = {
                "status": str(result["status"]),
                "cycle": cycle,
                "run_id": run_id,
                "metrics": dict(result.get("metrics") or {}),
            }
            if self._state["status"] in TERMINAL_STATUSES:
                return dict(self._state)
            observed_revision = self._wake_revision
            try:
                await workflow.wait_condition(
                    lambda revision=observed_revision: self._wake_revision > revision
                    or self._cancel_requested,
                    timeout=timedelta(seconds=30),
                )
            except TimeoutError:
                pass
        self._state["status"] = "CANCEL_REQUESTED"
        return dict(self._state)
