from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.order import OrderStatus


class OrderItem(BaseModel):
    sku: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)


class OrderCreate(BaseModel):
    items: list[OrderItem]


class OrderUpdateStatus(BaseModel):
    status: OrderStatus


class OrderPublic(BaseModel):
    id: uuid.UUID
    user_id: int
    items: list[dict]
    total_price: float
    status: OrderStatus
    created_at: datetime

