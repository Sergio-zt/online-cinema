from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_maker, get_async_session
from src.modules.accounts.models import UserGroup, UserGroupEnum
from src.modules.accounts.router import router as accounts_router
from src.modules.cart.router import router as cart_router
from src.modules.movies.router import router as movies_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Execute startup and shutdown application lifecycle events."""
    # Seed default user groups if they do not exist
    async with async_session_maker() as session:
        for group_role in UserGroupEnum:
            query = select(UserGroup).where(UserGroup.name == group_role)
            existing_group = await session.scalar(query)
            if not existing_group:
                session.add(UserGroup(name=group_role))
        await session.commit()

    yield


app = FastAPI(
    title="Online Cinema API",
    version="0.1.0",
    description="Backend API for online cinema platform",
    lifespan=lifespan,
)

# Register routers
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(movies_router, prefix="/api/v1")
app.include_router(cart_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, str]:
    """Check health status and verify database connectivity."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
