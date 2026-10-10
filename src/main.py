import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_maker, get_async_session
from src.modules.accounts.models import UserGroup, UserGroupEnum
from src.modules.accounts.router import router as accounts_router
from src.modules.cart.router import router as cart_router
from src.modules.movies.router import router as movies_router
from src.modules.orders.router import router as orders_router
from src.modules.payments.router import router as payments_router

docs_security = HTTPBasic()


def verify_docs_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(docs_security)],
) -> str:
    """Validate HTTP Basic credentials to restrict Swagger/OpenAPI documentation access."""
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "cinema_admin")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


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


# Initialize app with default docs disabled to enforce access control
app = FastAPI(
    title="Online Cinema API",
    version="1.0.0",
    description="Secured backend API for online cinema platform",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# Register routers
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(movies_router, prefix="/api/v1")
app.include_router(cart_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")


# Protected documentation endpoints
@app.get("/docs", include_in_schema=False)
async def get_swagger_ui(
    username: Annotated[str, Depends(verify_docs_credentials)],
):
    """Protected Swagger UI documentation endpoint."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title="Online Cinema API - Docs"
    )


@app.get("/redoc", include_in_schema=False)
async def get_redoc_ui(
    username: Annotated[str, Depends(verify_docs_credentials)],
):
    """Protected ReDoc documentation endpoint."""
    return get_redoc_html(
        openapi_url="/openapi.json", title="Online Cinema API - ReDoc"
    )


@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_schema(
    username: Annotated[str, Depends(verify_docs_credentials)],
):
    """Protected OpenAPI specification endpoint."""
    return JSONResponse(
        get_openapi(title=app.title, version=app.version, routes=app.routes)
    )


@app.get("/health", tags=["Health"])
async def health_check(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, str]:
    """Check health status and verify database connectivity."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
