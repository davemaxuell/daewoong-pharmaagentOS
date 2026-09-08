from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.dependencies import session_dependency
from app.models import ResearchRun
from app.security.auth import Principal, rag_principal

from .schemas import CreateResearch
from .service import control_run, create_run, detail, owned_run, summary

router = APIRouter(prefix="/research/runs", tags=["FDA Research"])


def private(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


@router.post("", status_code=201)
async def create_research(
    payload: CreateResearch,
    request: Request,
    response: Response,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
):
    private(response)
    if not request.app.state.settings.research_agent_enabled:
        raise HTTPException(503, "FDA research is not available yet")
    if request.app.state.research_model is None:
        raise HTTPException(503, "Research AI is unavailable; try again later")
    run = await create_run(session, principal.subject, payload)
    return await detail(session, run)


@router.get("")
async def list_research(
    response: Response,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
):
    private(response)
    runs = (
        await session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.owner_id == principal.subject,
            )
            .options(defer(ResearchRun.checkpoint), defer(ResearchRun.result))
            .order_by(ResearchRun.updated_at.desc(), ResearchRun.id)
            .limit(30)
        )
    ).all()
    return {"items": [summary(run) for run in runs]}


@router.get("/{run_id}")
async def get_research(
    run_id: UUID,
    response: Response,
    after: int = Query(default=0, ge=0, le=10_000),
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
):
    private(response)
    return await detail(session, await owned_run(session, str(run_id), principal.subject), after)


@router.post("/{run_id}/{action}")
async def control_research(
    run_id: UUID,
    action: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(rag_principal),
    session: AsyncSession = Depends(session_dependency),
):
    private(response)
    if action not in {"stop", "resume"}:
        raise HTTPException(404, "Unknown research action")
    if action == "resume" and (
        not request.app.state.settings.research_agent_enabled
        or request.app.state.research_model is None
    ):
        raise HTTPException(503, "Research AI is unavailable; try again later")
    run = await control_run(session, str(run_id), principal.subject, action)
    return await detail(session, run)
