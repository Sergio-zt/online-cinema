from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class OrderStatusEnum(str, enum.Enum):
    """Lifecycle statuses for customer orders."""

    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"


class Order(Base):
    """Customer order containing one or more movies."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum, name="order_status_enum"),
        default=OrderStatusEnum.PENDING,
        nullable=False,
        index=True,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", backref="orders")
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    payments = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    """Individual line item within an order preserving price at order time."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movie_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("movies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_at_order: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="items")
    movie = relationship("Movie", lazy="joined")
