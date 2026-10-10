from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.database import get_async_session
from src.main import app
from src.modules.accounts.models import UserGroup, UserGroupEnum

# Create test engine with NullPool to prevent asyncpg
# connection sharing across asyncio loops
test_engine = create_async_engine(
    settings.async_database_url,
    poolclass=NullPool,
)
test_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Override database session dependency with NullPool test session."""
    async with test_session_maker() as session:
        yield session


app.dependency_overrides[get_async_session] = override_get_async_session


@pytest.fixture(autouse=True)
def mock_celery_send_email():
    """Mock Celery task to avoid real network/SMTP calls during test runs."""
    with patch(
        "src.tasks.email.send_email_task.delay", return_value=MagicMock()
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
async def seed_user_groups() -> None:
    """Ensure all system roles exist so tests don't depend on DB state."""
    async with test_session_maker() as session:
        existing = set(await session.scalars(select(UserGroup.name)))
        for role in UserGroupEnum:
            if role not in existing:
                session.add(UserGroup(name=role))
        await session.commit()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a dedicated asynchronous database session for test assertions."""
    async with test_session_maker() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client fixture configured for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
