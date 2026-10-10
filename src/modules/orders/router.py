from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.modules.accounts.dependencies import (
    get_current_active_user,
    require_roles,
)
from src.modules.accounts.models import User, UserGroupEnum
from src.modules.orders.models import OrderStatusEnum
from src.modules.orders.schemas import OrderResponse
from src.modules.orders.service import OrdersService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_orders_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> OrdersService:
    """Dependency providing OrdersService instance."""
    return OrdersService(session)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order from cart",
)
async def create_order(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderResponse:
    """Place a new order containing all current movies in the user's shopping cart."""
    return await service.create_order_from_cart(current_user.id)


@router.get(
    "",
    response_model=list[OrderResponse],
    summary="List customer orders",
)
async def list_orders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> list[OrderResponse]:
    """Retrieve full history of orders placed by the current user."""
    return await service.list_user_orders(current_user.id)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order details",
)
async def get_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderResponse:
    """Retrieve a specific order by ID."""
    return await service.get_order_by_id(order_id, current_user.id)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel a pending order",
)
async def cancel_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderResponse:
    """Cancel an unpaid order before payment completes."""
    return await service.cancel_order(order_id, current_user.id)


@router.get(
    "/admin/all",
    response_model=list[OrderResponse],
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Filter all platform orders (Moderator/Admin)",
)
async def admin_list_orders(
    service: Annotated[OrdersService, Depends(get_orders_service)],
    user_id: Optional[int] = Query(default=None),
    status_filter: Optional[OrderStatusEnum] = Query(default=None, alias="status"),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
) -> list[OrderResponse]:
    """Allow administrators to view and filter orders across all users."""
    return await service.admin_list_orders(
        user_id=user_id,
        status_filter=status_filter,
        created_from=date_from,
        created_to=date_to,
    )
