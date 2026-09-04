from __future__ import annotations

import logging

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import TLSConfig

from app.config import Settings

logger = logging.getLogger(__name__)


def temporal_tls(settings: Settings) -> bool | TLSConfig:
    if not settings.temporal_tls_enabled:
        return False
    if not (
        settings.temporal_tls_ca_path
        and settings.temporal_tls_cert_path
        and settings.temporal_tls_key_path
    ):
        raise RuntimeError("Temporal TLS is enabled without CA, certificate, and key paths")
    return TLSConfig(
        server_root_ca_cert=settings.temporal_tls_ca_path.read_bytes(),
        client_cert=settings.temporal_tls_cert_path.read_bytes(),
        client_private_key=settings.temporal_tls_key_path.read_bytes(),
    )


async def start_or_wake_case_workflow(settings: Settings, run_id: str) -> None:
    """Idempotently start the outer workflow or wake the existing durable instance."""

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        tls=temporal_tls(settings),
        identity="pharma-api-temporal-dispatcher",
    )
    workflow_id = f"pharma-case-{run_id}"
    try:
        await client.start_workflow(
            "PharmaCaseOuterWorkflow",
            {"run_id": run_id},
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
    except WorkflowAlreadyStartedError:
        await client.get_workflow_handle(workflow_id).signal("wake")


async def best_effort_start_or_wake(settings: Settings, run_id: str) -> None:
    if not settings.temporal_enabled:
        return
    try:
        await start_or_wake_case_workflow(settings, run_id)
    except Exception:
        # The transactional database queue remains a safe outbox/fallback; the
        # outage is surfaced via telemetry/logs and the workflow can be replayed.
        logger.exception("Temporal dispatch failed for durable run %s", run_id)
