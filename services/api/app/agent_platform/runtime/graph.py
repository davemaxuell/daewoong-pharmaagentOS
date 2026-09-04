from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

RunDirective = Literal[
    "CANCEL",
    "PAUSE",
    "HOLD",
    "REQUEST_APPROVAL",
    "DISPATCH",
    "COMPLETE",
    "BLOCK",
]


class RunGraphState(TypedDict):
    """JSON-safe orchestration state persisted in ``CaseRun.checkpoint``.

    The model never chooses transitions.  This state is evaluated by a pure
    deterministic graph and the service layer persists each resulting state
    change before work is made available to a specialist.
    """

    schema_version: str
    checkpoint_version: int
    run_id: str
    case_id: str
    plan_id: str
    plan_version: int
    plan_sha256: str
    bound_state_hash: str
    workflow_template: dict[str, Any]
    step_definitions: list[dict[str, Any]]
    steps: dict[str, dict[str, Any]]
    step_key: str | None
    control: dict[str, Any]
    budget: dict[str, Any]
    directive: RunDirective


def _apply_control(state: RunGraphState) -> dict[str, Any]:
    control = state.get("control") or {}
    if control.get("cancel_requested"):
        return {"directive": "CANCEL", "step_key": state.get("step_key")}
    if control.get("pause_requested"):
        return {"directive": "PAUSE", "step_key": state.get("step_key")}
    return {"directive": "HOLD"}


def _control_route(state: RunGraphState) -> Literal["stop", "schedule"]:
    return "stop" if state["directive"] in {"CANCEL", "PAUSE"} else "schedule"


def _select_step(state: RunGraphState) -> dict[str, Any]:
    definitions = state.get("step_definitions") or []
    step_states = state.get("steps") or {}

    for definition in definitions:
        key = str(definition["step_key"])
        status = str((step_states.get(key) or {}).get("status", "PENDING"))
        if status in {"RUNNING", "WAITING_FOR_APPROVAL"}:
            return {"directive": "HOLD", "step_key": key}

    if definitions and all(
        str((step_states.get(str(item["step_key"])) or {}).get("status")) == "COMPLETED"
        for item in definitions
    ):
        return {"directive": "COMPLETE", "step_key": None}

    for definition in definitions:
        key = str(definition["step_key"])
        state_for_step = step_states.get(key) or {}
        if state_for_step.get("status", "PENDING") != "PENDING":
            continue
        dependencies = [str(value) for value in definition.get("depends_on") or []]
        if all(
            (step_states.get(value) or {}).get("status") == "COMPLETED"
            for value in dependencies
        ):
            directive: RunDirective = (
                "REQUEST_APPROVAL" if definition.get("requires_approval") else "DISPATCH"
            )
            return {"directive": directive, "step_key": key}

    return {"directive": "BLOCK", "step_key": None}


@lru_cache(maxsize=1)
def orchestrator_graph():
    """Return the compiled deterministic inner graph.

    PostgreSQL/SQLite remain the authoritative durable checkpointer for this
    staged deployment.  A LangGraph thread can therefore be reconstructed from
    the versioned JSON checkpoint without serializing credentials or ORM state.
    """

    builder = StateGraph(RunGraphState)
    builder.add_node("apply_control", _apply_control)
    builder.add_node("select_step", _select_step)
    builder.add_edge(START, "apply_control")
    builder.add_conditional_edges(
        "apply_control",
        _control_route,
        {"stop": END, "schedule": "select_step"},
    )
    builder.add_edge("select_step", END)
    return builder.compile(name="pharma-agent-case-orchestrator")


def evaluate_run_state(state: RunGraphState) -> RunGraphState:
    return orchestrator_graph().invoke(state)
