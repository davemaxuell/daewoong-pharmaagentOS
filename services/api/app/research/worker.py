from __future__ import annotations

import asyncio
import copy
import json
import re
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import or_, select

from app.ai import AiGenerationError
from app.models import ResearchRun, new_uuid, utcnow

from .provider import build_research_model
from .schemas import MAX_EVIDENCE, MAX_MODEL_CALLS, MAX_TOTAL_TOKENS, TOOL_MODELS
from .service import add_event
from .tools import evidence_is_current, read_sources, search_sources


class LeaseLost(Exception):
    pass


class BudgetReached(Exception):
    pass


async def mutate(database, run_id, lease_id, operation):
    async with database.session_factory() as session:
        run = await session.scalar(
            select(ResearchRun)
            .where(
                ResearchRun.id == run_id,
            )
            .with_for_update()
        )
        if not run or run.status != "running" or run.lease_id != lease_id:
            raise LeaseLost()
        operation(session, run)
        run.updated_at = utcnow()
        await session.commit()


async def claim(database):
    async with database.session_factory() as session:
        run = await session.scalar(
            select(ResearchRun)
            .where(
                or_(
                    ResearchRun.status == "queued",
                    (ResearchRun.status == "running") & (ResearchRun.lease_expires_at < utcnow()),
                )
            )
            .order_by(ResearchRun.created_at, ResearchRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not run:
            return None
        recovered = run.status == "running"
        run.status = "running"
        run.lease_id = new_uuid()
        run.lease_expires_at = utcnow() + timedelta(seconds=150)
        run.started_at = run.started_at or utcnow()
        add_event(session, run, "recovered" if recovered else "started")
        await session.commit()
        return run


async def event(database, run, kind, *, stage=None, data=None):
    await mutate(
        database,
        run.id,
        run.lease_id,
        lambda session, current: add_event(session, current, kind, data, stage),
    )


async def reserve(database, run, input_value, max_output=4_000):
    # UTF-8 bytes bound input tokens conservatively. Reserve before the network
    # call so a terminated worker cannot repeatedly spend unaccounted model calls.
    allowance = len(json.dumps(input_value, ensure_ascii=False).encode()) + max_output + 3_000

    def update(_session, current):
        if (
            current.model_calls >= MAX_MODEL_CALLS
            or current.total_tokens + allowance > MAX_TOTAL_TOKENS
        ):
            raise BudgetReached()
        current.model_calls += 1
        current.total_tokens += allowance
        current.lease_expires_at = utcnow() + timedelta(seconds=150)
        run.model_calls = current.model_calls

    await mutate(database, run.id, run.lease_id, update)
    return allowance


async def record_usage(database, run, allowance, tokens):
    def update(_session, current):
        # Missing/invalid usage leaves the conservative reservation in place.
        if isinstance(tokens, int) and 0 < tokens <= allowance:
            current.total_tokens -= allowance - tokens

    await mutate(database, run.id, run.lease_id, update)


async def finish(database, run, status, code=None, result=None):
    def update(session, current):
        current.status = status
        current.error_code = code
        current.result = result
        current.finished_at = utcnow()
        current.lease_id = None
        current.lease_expires_at = None
        add_event(
            session,
            current,
            status,
            {"code": code} if code else {},
            "complete" if status == "completed" else None,
        )

    await mutate(database, run.id, run.lease_id, update)


async def execute_tool(database, model, run, state, proposal):
    name = proposal.name
    validator = TOOL_MODELS.get(name)
    if not validator:
        return {"error": "unknown_tool"}, None
    try:
        args = validator.model_validate(proposal.arguments)
    except ValidationError:
        return {"error": "invalid_arguments", "instruction": "Follow the tool schema."}, None
    if name != "plan_research" and not state.get("plan"):
        return {"error": "plan_required"}, None

    if name == "plan_research":
        if state.get("plan"):
            return {"error": "plan_already_saved"}, None
        if run.language == "ko" and any(not re.search(r"[가-힣]", step) for step in args.steps):
            return {
                "error": "plan_language_mismatch",
                "instruction": "Call plan_research again with every action step written in Korean.",
            }, None
        state["plan"] = args.steps
        await event(database, run, "plan_saved", stage="planning", data={"steps": args.steps})
        return {"saved": True, "next": "Search the saved sources."}, None

    if name == "search_sources":
        if state.get("searches", 0) >= 4:
            return {
                "error": "search_limit",
                "next": "Use retained results or report no evidence.",
            }, None
        await event(database, run, "search_started", stage="searching", data={"query": args.query})
        found = await search_sources(database, args.query)
        state["searches"] = state.get("searches", 0) + 1
        candidates = {item["chunk_id"]: item for item in state.get("candidates", [])}
        candidates.update({item["chunk_id"]: item for item in found})
        state["candidates"] = list(candidates.values())[:32]
        await event(
            database, run, "search_completed", data={"query": args.query, "count": len(found)}
        )
        return {"matches": found, "note": "Read selected chunk IDs before citing them."}, None

    if name == "read_sources":
        ids = list(dict.fromkeys(str(value) for value in args.chunk_ids))
        allowed = {item["chunk_id"] for item in state.get("candidates", [])}
        if not set(ids).issubset(allowed):
            return {"error": "source_not_in_search_results"}, None
        retained = {item["chunk_id"]: item for item in state.get("evidence", [])}
        if len(set(retained) | set(ids)) > MAX_EVIDENCE:
            return {"error": "source_limit", "next": "Write using the retained evidence."}, None
        await event(database, run, "read_started", stage="reading", data={"count": len(ids)})
        records = await read_sources(database, ids)
        for item in records:
            if item["chunk_id"] in retained:
                item["id"] = retained[item["chunk_id"]]["id"]
            else:
                item["id"] = f"S{len(retained) + 1}"
            retained[item["chunk_id"]] = item
        state["evidence"] = list(retained.values())
        selected = [retained[key] for key in ids if key in retained]
        await event(
            database,
            run,
            "read_completed",
            data={
                "count": len(selected),
                "sources": [
                    {key: item[key] for key in ("id", "company", "letter_id", "anchor")}
                    for item in selected
                ],
            },
        )
        return {"sources": selected}, None

    if name == "report_no_evidence":
        if state.get("searches", 0) < 2:
            return {"error": "try_an_alternative_search_first"}, None
        return {"explanation": args.explanation}, "insufficient_evidence"

    evidence = state.get("evidence", [])
    cited_ids = {value for finding in args.findings for value in finding.citation_ids}
    sources = [item for item in evidence if item["id"] in cited_ids]
    if not evidence or cited_ids != {item["id"] for item in sources}:
        return {"error": "invalid_citations", "allowed_ids": [s["id"] for s in evidence]}, None
    if state.get("checks", 0) >= 2:
        return {"error": "evidence_check_limit"}, "insufficient_evidence"
    await event(database, run, "draft_prepared", stage="writing", data={"title": args.title})
    await event(database, run, "check_started", stage="checking", data={"count": len(cited_ids)})
    if not await evidence_is_current(database, sources):
        return {"error": "source_changed", "next": "Read the source again before writing."}, None
    brief = args.model_dump(mode="json")
    allowance = await reserve(database, run, {"brief": brief, "evidence": sources}, 1_500)
    check, tokens = await model.verify(brief, sources, run.language)
    await record_usage(database, run, allowance, tokens)
    state["checks"] = state.get("checks", 0) + 1
    if not check.supported or check.issues:
        await event(database, run, "check_needs_revision", data={"issues": check.issues[:8]})
        return {"error": "revise_unsupported_findings", "issues": check.issues[:8]}, None
    # Source changes during verification also invalidate completion.
    if not await evidence_is_current(database, sources):
        return {"error": "source_changed", "next": "Read the source again."}, None
    await event(database, run, "check_completed", data={"count": len(cited_ids)})
    return {
        **brief,
        "sources": sources,
        "evidence_check": "ai_checked",
        "intended_use": "human_review_draft",
    }, "completed"


async def execute_run(database, model, run):
    state = copy.deepcopy(run.checkpoint or {})
    conversation = state.setdefault(
        "conversation",
        [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "objective": run.objective,
                        "language": run.language,
                        "scope": "Saved FDA Drug warning letters; prepare a human review draft.",
                    },
                    ensure_ascii=False,
                ),
            }
        ],
    )
    while True:
        await event(database, run, "choosing_action")
        allowance = await reserve(database, run, conversation)
        proposal = await model.propose(conversation, MAX_MODEL_CALLS - run.model_calls)
        await record_usage(database, run, allowance, proposal.tokens)
        observation, terminal = await execute_tool(database, model, run, state, proposal)
        # Preserve native call IDs and encrypted reasoning for Responses replay.
        # This private checkpoint is never included in the browser response.
        conversation.extend(proposal.output)
        conversation.append(
            {
                "type": "function_call_output",
                "call_id": proposal.call_id,
                "output": json.dumps(observation, ensure_ascii=False),
            }
        )

        def save(session, current, observation=observation):
            current.checkpoint = copy.deepcopy(state)
            if "error" in observation:
                add_event(
                    session,
                    current,
                    "action_needs_revision",
                    {
                        "code": observation["error"],
                    },
                )

        await mutate(database, run.id, run.lease_id, save)
        if terminal:
            await finish(database, run, terminal, result=observation)
            return


async def run_research_slice(database, settings, *, model=None, slice_seconds=195):
    if not settings.research_agent_enabled:
        return {"processed": 0, "disabled": True}
    model = model or build_research_model(settings)
    if model is None:
        return {"processed": 0, "unavailable": True}
    run = await claim(database)
    if run is None:
        return {"processed": 0}
    try:
        async with asyncio.timeout(slice_seconds):
            await execute_run(database, model, run)
    except LeaseLost:
        return {"processed": 1, "stopped_or_reclaimed": True}
    except BudgetReached:
        try:
            await finish(database, run, "limit_reached", "execution_budget")
        except LeaseLost:
            pass
    except (AiGenerationError, ValueError, TypeError, KeyError):
        try:
            await finish(database, run, "failed", "model_unavailable")
        except LeaseLost:
            pass
    except TimeoutError:

        def release(session, current):
            current.status = "queued"
            current.lease_id = None
            current.lease_expires_at = None
            add_event(session, current, "checkpoint_saved")

        try:
            await mutate(database, run.id, run.lease_id, release)
        except LeaseLost:
            pass
    return {"processed": 1}
