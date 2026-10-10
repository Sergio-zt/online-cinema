from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.modules.payments.models import PaymentStatusEnum


class CheckoutSessionResponse(BaseModel):
    """Schema returning Stripe checkout redirect URL and session ID."""

    checkout_url: str
    session_id: str


class PaymentItemResponse(BaseModel):
    """Schema representing an item covered by a payment transaction."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_item_id: int
    price_at_payment: Decimal


class PaymentResponse(BaseModel):
    """Schema representing a payment transaction record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    order_id: int
    amount: Decimal
    status: PaymentStatusEnum
    external_payment_id: Optional[str] = None
    created_at: datetime
    items: list[PaymentItemResponse] = []
