from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.modules.orders.models import OrderStatusEnum


class OrderItemResponse(BaseModel):
    """Schema representing an item inside an order."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    movie_title: Optional[str] = None
    price_at_order: Decimal


class OrderResponse(BaseModel):
    """Schema representing full order details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: OrderStatusEnum
    total_amount: Decimal
    created_at: datetime
    items: list[OrderItemResponse] = []
