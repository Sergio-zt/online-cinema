from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.cart.models import Cart, CartItem
from src.modules.cart.schemas import CartItemResponse, CartResponse
from src.modules.movies.models import Movie
from src.modules.orders.models import Order, OrderItem, OrderStatusEnum


class CartService:
    """Service handling business logic for shopping carts and items."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_cart(self, user_id: int) -> Cart:
        """Fetch existing cart or create a new one for the user."""
        query = select(Cart).where(Cart.user_id == user_id)
        cart = await self.session.scalar(query)
        if not cart:
            cart = Cart(user_id=user_id)
            self.session.add(cart)
            await self.session.commit()
            await self.session.refresh(cart)
        return cart

    async def get_user_cart_response(self, user_id: int) -> CartResponse:
        """Construct full cart response querying active
        cart items freshly from database."""
        cart = await self.get_or_create_cart(user_id)

        items_query = (
            select(CartItem)
            .where(CartItem.cart_id == cart.id)
            .options(selectinload(CartItem.movie).selectinload(Movie.genres))
            .order_by(CartItem.added_at.desc())
        )
        cart_items = (await self.session.scalars(items_query)).all()

        items_response: list[CartItemResponse] = []
        total_price = Decimal("0.00")

        for item in cart_items:
            movie = item.movie
            if movie:
                genres = [g.name for g in movie.genres]
                items_response.append(
                    CartItemResponse(
                        id=item.id,
                        movie_id=movie.id,
                        movie_title=movie.name,
                        movie_price=movie.price,
                        movie_year=movie.year,
                        movie_genres=genres,
                        added_at=item.added_at,
                    )
                )
                total_price += movie.price

        return CartResponse(
            id=cart.id,
            user_id=cart.user_id,
            items=items_response,
            total_items=len(items_response),
            total_price=total_price,
        )

    async def is_movie_purchased_by_user(self, user_id: int, movie_id: int) -> bool:
        """Check whether the user has already purchased this movie."""
        query = (
            select(OrderItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatusEnum.PAID,
                OrderItem.movie_id == movie_id,
            )
        )
        result = await self.session.scalar(query)
        return result is not None

    async def add_item_to_cart(self, user_id: int, movie_id: int) -> CartResponse:
        """Add a movie to user cart after verifying purchase history and uniqueness."""
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        already_purchased = await self.is_movie_purchased_by_user(user_id, movie_id)
        if already_purchased:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "You have already purchased this movie. "
                    "Repeat purchases are not allowed."
                ),
            )

        cart = await self.get_or_create_cart(user_id)

        existing_item = await self.session.scalar(
            select(CartItem).where(
                CartItem.cart_id == cart.id, CartItem.movie_id == movie_id
            )
        )
        if existing_item:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Movie is already present in your shopping cart.",
            )

        new_item = CartItem(cart_id=cart.id, movie_id=movie_id)
        self.session.add(new_item)
        await self.session.commit()

        return await self.get_user_cart_response(user_id)

    async def remove_item_from_cart(self, user_id: int, movie_id: int) -> CartResponse:
        """Remove a single movie item from the user's shopping cart."""
        cart = await self.get_or_create_cart(user_id)
        item = await self.session.scalar(
            select(CartItem).where(
                CartItem.cart_id == cart.id, CartItem.movie_id == movie_id
            )
        )
        if item:
            await self.session.delete(item)
            await self.session.commit()

        return await self.get_user_cart_response(user_id)

    async def clear_cart(self, user_id: int) -> CartResponse:
        """Completely clear all items from the user's cart."""
        cart = await self.get_or_create_cart(user_id)
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await self.session.commit()
        return await self.get_user_cart_response(user_id)

    async def admin_get_user_cart(self, target_user_id: int) -> CartResponse:
        """Allow administrators to view any user's cart for
        analysis or troubleshooting."""
        return await self.get_user_cart_response(target_user_id)
