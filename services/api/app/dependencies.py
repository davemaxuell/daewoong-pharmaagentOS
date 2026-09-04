from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AiGenerator
from app.config import Settings
from app.embeddings import GeminiEmbeddingGenerator


def settings_dependency(request: Request) -> Settings:
    return request.app.state.settings


def ai_generator_dependency(request: Request) -> AiGenerator | None:
    return request.app.state.ai_generator


def embedding_generator_dependency(request: Request) -> GeminiEmbeddingGenerator | None:
    return request.app.state.embedding_generator


async def session_dependency(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
