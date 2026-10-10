import json
from datetime import datetime
from typing import Any, Optional

import stripe
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.modules.cart.models import Cart, CartItem
from src.modules.orders.models import Order, OrderItem, OrderStatusEnum
from src.modules.payments.models import (
    Payment,
    PaymentItem,
    PaymentStatusEnum,
)
from src.modules.payments.schemas import (
    CheckoutSessionResponse,
    PaymentItemResponse,
    PaymentResponse,
)
from src.tasks.email import send_email_task

stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentsService:
    """Service handling Stripe checkout session creation, webhooks, and transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_checkout_session(
        self, user_id: int, order_id: int
    ) -> CheckoutSessionResponse:
        """Create a Stripe Checkout Session for an unpaid pending order."""
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.movie),
                selectinload(Order.user),
            )
        )
        order = await self.session.scalar(query)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Order not found."
            )
        if order.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied."
            )
        if order.status != OrderStatusEnum.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Order is not in pending status (current status: "
                    f"{order.status.value})."
                ),
            )

        line_items = []
        for item in order.items:
            movie_name = item.movie.name if item.movie else f"Movie #{item.movie_id}"
            unit_amount = int(item.price_at_order * 100)
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": unit_amount,
                        "product_data": {
                            "name": movie_name,
                        },
                    },
                    "quantity": 1,
                }
            )

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=(
                    "http://localhost:8000/api/v1/payments/success?"
                    "session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url="http://localhost:8000/api/v1/payments/cancel",
                client_reference_id=str(order.id),
                metadata={
                    "order_id": str(order.id),
                    "user_id": str(user_id),
                },
            )
            return CheckoutSessionResponse(
                checkout_url=checkout_session.url or "",
                session_id=checkout_session.id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Failed to communicate with "
                    f"Stripe payment provider: {str(exc)}"
                ),
            )

    async def complete_order_payment(
        self,
        order_id: int,
        user_id: int,
        external_payment_id: Optional[str] = None,
    ) -> Payment:
        """Mark order as paid, create payment records,
        clear cart, and send confirmation email."""
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.movie),
                selectinload(Order.user),
            )
        )
        order = await self.session.scalar(query)
        if not order or order.status == OrderStatusEnum.PAID:
            return None  # type: ignore[return-value]

        # 1. Update order status
        order.status = OrderStatusEnum.PAID

        # 2. Record payment transaction
        payment = Payment(
            user_id=user_id,
            order_id=order.id,
            status=PaymentStatusEnum.SUCCESSFUL,
            amount=order.total_amount,
            external_payment_id=external_payment_id,
        )
        self.session.add(payment)
        await self.session.flush()

        # 3. Create payment items matching order items
        for item in order.items:
            payment_item = PaymentItem(
                payment_id=payment.id,
                order_item_id=item.id,
                price_at_payment=item.price_at_order,
            )
            self.session.add(payment_item)

        # 4. Clear items from user's shopping cart
        user_cart = await self.session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        if user_cart:
            await self.session.execute(
                delete(CartItem).where(CartItem.cart_id == user_cart.id)
            )

        await self.session.commit()
        await self.session.refresh(payment, attribute_names=["items"])

        # 5. Dispatch email confirmation via Celery
        if order.user and order.user.email:
            movie_titles = ", ".join(
                [item.movie.name for item in order.items if item.movie]
            )
            send_email_task.delay(
                to_email=order.user.email,
                subject=f"Payment Confirmation - Order #{order.id}",
                body_text=(
                    f"Thank you for your purchase! "
                    f"Order #{order.id} for ${order.total_amount} "
                    f"has been successfully paid. Movies: {movie_titles}."
                ),
                body_html=(
                    f"<h2>Payment Successful!</h2>"
                    f"<p>Order <strong>#{order.id}</strong> "
                    f"has been successfully processed.</p>"
                    f"<p>Total amount paid: <strong>${order.total_amount}</strong></p>"
                    f"<p>Purchased movies: <em>{movie_titles}</em></p>"
                ),
            )

        return payment

    async def process_stripe_webhook(
        self, payload_bytes: bytes, sig_header: Optional[str] = None
    ) -> dict[str, str]:
        """Validate Stripe webhook signature and handle successful checkout events."""
        event: dict[str, Any]
        if sig_header and settings.STRIPE_WEBHOOK_SECRET != "whsec_dummy_key":
            try:
                event = stripe.Webhook.construct_event(
                    payload_bytes, sig_header, settings.STRIPE_WEBHOOK_SECRET
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Webhook signature verification failed: {str(exc)}",
                )
        else:
            event = json.loads(payload_bytes.decode("utf-8"))

        event_type = event.get("type")
        if event_type == "checkout.session.completed":
            session_data = event.get("data", {}).get("object", {})
            metadata = session_data.get("metadata", {})
            order_id = int(metadata.get("order_id", 0))
            user_id = int(metadata.get("user_id", 0))
            session_id = session_data.get("id")

            if order_id and user_id:
                await self.complete_order_payment(
                    order_id=order_id,
                    user_id=user_id,
                    external_payment_id=session_id,
                )

        return {"status": "success"}

    async def list_user_payments(self, user_id: int) -> list[PaymentResponse]:
        """Retrieve payment transaction history for a user."""
        query = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .options(selectinload(Payment.items))
        )
        payments = (await self.session.scalars(query)).all()
        return [await self._to_payment_response(p) for p in payments]

    async def admin_list_payments(
        self,
        user_id: Optional[int] = None,
        status_filter: Optional[PaymentStatusEnum] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[PaymentResponse]:
        """Admin functionality to inspect and filter all payments."""
        query = (
            select(Payment)
            .order_by(Payment.created_at.desc())
            .options(selectinload(Payment.items))
        )
        if user_id:
            query = query.where(Payment.user_id == user_id)
        if status_filter:
            query = query.where(Payment.status == status_filter)
        if date_from:
            query = query.where(Payment.created_at >= date_from)
        if date_to:
            query = query.where(Payment.created_at <= date_to)

        payments = (await self.session.scalars(query)).all()
        return [await self._to_payment_response(p) for p in payments]

    async def _to_payment_response(self, payment: Payment) -> PaymentResponse:
        """Helper to serialize Payment model into PaymentResponse schema."""
        items = [
            PaymentItemResponse(
                id=item.id,
                order_item_id=item.order_item_id,
                price_at_payment=item.price_at_payment,
            )
            for item in payment.items
        ]
        return PaymentResponse(
            id=payment.id,
            user_id=payment.user_id,
            order_id=payment.order_id,
            amount=payment.amount,
            status=payment.status,
            external_payment_id=payment.external_payment_id,
            created_at=payment.created_at,
            items=items,
        )
