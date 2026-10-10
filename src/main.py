from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session

app = FastAPI(
    title="Online Cinema API",
    version="0.1.0",
    description="Backend API for online cinema platform",
)


@app.get("/health", tags=["Health"])
async def health_check(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, str]:
    """Check health status and verify database connectivity."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
