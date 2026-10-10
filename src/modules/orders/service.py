from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.cart.models import Cart, CartItem
from src.modules.orders.models import Order, OrderItem, OrderStatusEnum
from src.modules.orders.schemas import OrderItemResponse, OrderResponse


class OrdersService:
    """Service handling business logic for customer orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_order_from_cart(self, user_id: int) -> OrderResponse:
        """Create a new order from current cart items with
        validations and price locking."""
        cart_query = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(selectinload(Cart.items).selectinload(CartItem.movie))
        )
        cart = await self.session.scalar(cart_query)
        if not cart or not cart.items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your shopping cart is empty.",
            )

        movie_ids = [item.movie_id for item in cart.items]

        # Check if user already purchased any of these movies
        purchased_query = (
            select(OrderItem.movie_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatusEnum.PAID,
                OrderItem.movie_id.in_(movie_ids),
            )
        )
        already_purchased_ids = (await self.session.scalars(purchased_query)).all()
        if already_purchased_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more movies in your cart have already been purchased.",
            )

        # Check for parallel pending orders with overlapping movies
        pending_orders_query = (
            select(OrderItem.movie_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatusEnum.PENDING,
                OrderItem.movie_id.in_(movie_ids),
            )
        )
        pending_overlap_ids = (await self.session.scalars(pending_orders_query)).all()
        if pending_overlap_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "An active pending order already contains some of these movies. "
                    "Please pay or cancel your previous pending order first."
                ),
            )

        total_amount = Decimal("0.00")
        order_items_to_add: list[OrderItem] = []

        for cart_item in cart.items:
            movie = cart_item.movie
            if not movie:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Movie with ID {cart_item.movie_id} is " "no longer available."
                    ),
                )
            total_amount += movie.price
            order_items_to_add.append(
                OrderItem(movie_id=movie.id, price_at_order=movie.price)
            )

        new_order = Order(
            user_id=user_id,
            status=OrderStatusEnum.PENDING,
            total_amount=total_amount,
        )
        self.session.add(new_order)
        await self.session.flush()

        for item in order_items_to_add:
            item.order_id = new_order.id
            self.session.add(item)

        await self.session.commit()
        await self.session.refresh(new_order, attribute_names=["items"])

        return await self._to_order_response(new_order)

    async def list_user_orders(self, user_id: int) -> list[OrderResponse]:
        """Retrieve list of orders for the specified user."""
        query = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .options(selectinload(Order.items).selectinload(OrderItem.movie))
        )
        orders = (await self.session.scalars(query)).all()
        return [await self._to_order_response(o) for o in orders]

    async def get_order_by_id(
        self, order_id: int, user_id: int, is_admin: bool = False
    ) -> OrderResponse:
        """Get single order by ID with ownership verification."""
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items).selectinload(OrderItem.movie))
        )
        order = await self.session.scalar(query)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Order not found."
            )
        if not is_admin and order.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied."
            )

        return await self._to_order_response(order)

    async def cancel_order(self, order_id: int, user_id: int) -> OrderResponse:
        """Cancel a pending order."""
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items).selectinload(OrderItem.movie))
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
                    "Only pending orders can be canceled. "
                    "Paid orders require a refund request."
                ),
            )

        order.status = OrderStatusEnum.CANCELED
        await self.session.commit()
        await self.session.refresh(order)
        return await self._to_order_response(order)

    async def admin_list_orders(
        self,
        user_id: Optional[int] = None,
        status_filter: Optional[OrderStatusEnum] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> list[OrderResponse]:
        """Admin functionality to filter all platform orders."""
        query = (
            select(Order)
            .order_by(Order.created_at.desc())
            .options(selectinload(Order.items).selectinload(OrderItem.movie))
        )

        if user_id:
            query = query.where(Order.user_id == user_id)
        if status_filter:
            query = query.where(Order.status == status_filter)
        if created_from:
            query = query.where(Order.created_at >= created_from)
        if created_to:
            query = query.where(Order.created_at <= created_to)

        orders = (await self.session.scalars(query)).all()
        return [await self._to_order_response(o) for o in orders]

    async def _to_order_response(self, order: Order) -> OrderResponse:
        """Helper to construct OrderResponse schema."""
        items: list[OrderItemResponse] = []
        for item in order.items:
            items.append(
                OrderItemResponse(
                    id=item.id,
                    movie_id=item.movie_id,
                    movie_title=item.movie.name if item.movie else None,
                    price_at_order=item.price_at_order,
                )
            )
        return OrderResponse(
            id=order.id,
            user_id=order.user_id,
            status=order.status,
            total_amount=order.total_amount,
            created_at=order.created_at,
            items=items,
        )
