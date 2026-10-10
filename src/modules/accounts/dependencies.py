from collections.abc import Callable, Awaitable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_async_session
from src.core.security import decode_jwt_token
from src.modules.accounts.models import User, UserGroupEnum

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/accounts/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Validate access token and return the authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_jwt_token(token)
        token_type: str = payload.get("type", "")
        user_id_str: str = payload.get("sub", "")
        if token_type != "access" or not user_id_str:
            raise credentials_exception
        user_id = int(user_id_str)
    except (PyJWTError, ValueError):
        raise credentials_exception

    query = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.group), selectinload(User.profile))
    )
    user = await session.scalar(query)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Verify that the authenticated user account is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account. Please activate your account.",
        )
    return current_user


def require_roles(
    *allowed_roles: UserGroupEnum,
) -> Callable[..., Awaitable[User]]:
    """Dependency factory enforcing role-based access control (RBAC)."""

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.group.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation.",
            )
        return current_user

    return role_checker
