import asyncio
from datetime import datetime, timezone
from typing import Any, cast

from celery import shared_task
from sqlalchemy import delete
from sqlalchemy.engine import CursorResult

from src.core.database import async_session_maker
from src.modules.accounts.models import ActivationToken


@shared_task(  # type: ignore[untyped-decorator]
    name="src.tasks.cleaners.clean_expired_activation_tokens"
)
def clean_expired_activation_tokens() -> int:
    """Periodic Celery Beat task to purge expired
    activation tokens from the database."""

    async def _clean() -> int:
        async with async_session_maker() as session:
            now_utc = datetime.now(timezone.utc)
            stmt = delete(ActivationToken).where(ActivationToken.expires_at < now_utc)
            result = await session.execute(stmt)
            await session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    return asyncio.run(_clean())
