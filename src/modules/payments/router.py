from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.modules.accounts.dependencies import (
    get_current_active_user,
    require_roles,
)
from src.modules.accounts.models import User, UserGroupEnum
from src.modules.payments.models import PaymentStatusEnum
from src.modules.payments.schemas import (
    CheckoutSessionResponse,
    PaymentResponse,
)
from src.modules.payments.service import PaymentsService

router = APIRouter(prefix="/payments", tags=["Payments"])


def get_payments_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PaymentsService:
    """Dependency providing PaymentsService instance."""
    return PaymentsService(session)


@router.post(
    "/checkout/{order_id}",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe Checkout Session",
)
async def create_checkout(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[PaymentsService, Depends(get_payments_service)],
) -> CheckoutSessionResponse:
    """Generate a Stripe checkout session URL for paying an order."""
    return await service.create_checkout_session(current_user.id, order_id)


@router.post(
    "/webhook",
    summary="Stripe payment webhook receiver",
)
async def stripe_webhook(
    request: Request,
    service: Annotated[PaymentsService, Depends(get_payments_service)],
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, str]:
    """Receive and process asynchronous Stripe payment events."""
    payload_bytes = await request.body()
    return await service.process_stripe_webhook(payload_bytes, stripe_signature)


@router.post(
    "/simulate-success/{order_id}",
    response_model=PaymentResponse,
    summary="Simulate successful payment for local testing",
)
async def simulate_payment(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[PaymentsService, Depends(get_payments_service)],
) -> PaymentResponse:
    """Local development endpoint to complete order
    payment without external Stripe calls."""
    payment = await service.complete_order_payment(
        order_id=order_id,
        user_id=current_user.id,
        external_payment_id="simulated_stripe_charge_id",
    )
    return await service._to_payment_response(payment)


@router.get(
    "",
    response_model=list[PaymentResponse],
    summary="List customer payments",
)
async def list_payments(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[PaymentsService, Depends(get_payments_service)],
) -> list[PaymentResponse]:
    """Retrieve full transaction history for the authenticated user."""
    return await service.list_user_payments(current_user.id)


@router.get(
    "/admin/all",
    response_model=list[PaymentResponse],
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Filter all payments (Moderator/Admin)",
)
async def admin_list_payments(
    service: Annotated[PaymentsService, Depends(get_payments_service)],
    user_id: Optional[int] = Query(default=None),
    status_filter: Optional[PaymentStatusEnum] = Query(default=None, alias="status"),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
) -> list[PaymentResponse]:
    """Allow administrators to view and filter payments platform-wide."""
    return await service.admin_list_payments(
        user_id=user_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
    )
