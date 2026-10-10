from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.modules.accounts.dependencies import (
    get_current_active_user,
    require_roles,
)
from src.modules.accounts.models import User, UserGroupEnum
from src.modules.cart.schemas import AddToCartRequest, CartResponse
from src.modules.cart.service import CartService

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])


def get_cart_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CartService:
    """Dependency providing CartService instance."""
    return CartService(session)


@router.get(
    "",
    response_model=CartResponse,
    summary="View shopping cart contents",
)
async def get_cart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    """Retrieve full shopping cart with items, prices, and total sum."""
    return await service.get_user_cart_response(current_user.id)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add movie to shopping cart",
)
async def add_item_to_cart(
    data: AddToCartRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    """Add a movie to cart verifying it has not been previously purchased."""
    return await service.add_item_to_cart(current_user.id, data.movie_id)


@router.delete(
    "/items/{movie_id}",
    response_model=CartResponse,
    summary="Remove movie from shopping cart",
)
async def remove_item_from_cart(
    movie_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    """Remove a specific movie item from user's shopping cart."""
    return await service.remove_item_from_cart(current_user.id, movie_id)


@router.delete(
    "",
    response_model=CartResponse,
    summary="Clear shopping cart entirely",
)
async def clear_cart(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    """Remove all items from the current user's shopping cart."""
    return await service.clear_cart(current_user.id)


# Administrator / Moderator endpoint
@router.get(
    "/admin/users/{user_id}",
    response_model=CartResponse,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="View user cart (Moderator/Admin)",
)
async def admin_get_user_cart(
    user_id: int,
    service: Annotated[CartService, Depends(get_cart_service)],
) -> CartResponse:
    """Allow moderators and administrators to inspect any user's cart."""
    return await service.admin_get_user_cart(user_id)
