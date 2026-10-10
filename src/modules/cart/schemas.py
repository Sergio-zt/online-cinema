from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CartItemResponse(BaseModel):
    """Schema representing an item inside a shopping cart."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    movie_title: str
    movie_price: Decimal
    movie_year: int
    movie_genres: list[str] = Field(default_factory=list)
    added_at: datetime


class CartResponse(BaseModel):
    """Schema representing full shopping cart details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    items: list[CartItemResponse]
    total_items: int
    total_price: Decimal


class AddToCartRequest(BaseModel):
    """Request payload for adding a movie to cart."""

    movie_id: int
