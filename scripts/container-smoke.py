"""Run inside the built API image with /tmp writable and no repository source mount."""
import asyncio
import os

from app.agent_platform.mcp.server import private_mcp_app
from app.agent_platform.registry.bundled import ensure_internal_agent_registry
from app.agent_platform.registry.workflows import ensure_bundled_workflow_template
from app.database import Database
from app.internal_knowledge.seed import load_synthetic_corpus
from app.models import AgentVersion, SkillVersion, ToolVersion
from sqlalchemy import func, select


async def main():
    assert os.getuid() != 0, "Runtime must not be root"
    database = Database("sqlite+aiosqlite:////tmp/container-smoke.db")
    try:
        await database.create_schema()
        async with database.session_factory() as session:
            await ensure_internal_agent_registry(session)
            await ensure_bundled_workflow_template(session)
            await session.commit()
            for model, expected in ((AgentVersion, 5), (SkillVersion, 10), (ToolVersion, 16)):
                assert await session.scalar(select(func.count()).select_from(model)) == expected
        assert load_synthetic_corpus()["assets"]
        assert private_mcp_app.openapi_url is None
        print("PASS: non-root image, registry 5/10/16, workflow, corpus, private gateway")
    finally:
        await database.dispose()


asyncio.run(main())
