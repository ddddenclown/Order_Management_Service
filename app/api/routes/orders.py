from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cache_get_order, cache_set_order
from app.core.redis import get_redis
from app.db.models.order import Order, OrderStatus
from app.db.models.user import User
from app.db.session import get_db
from app.messaging.rabbit import publisher
from app.schemas.order import OrderCreate, OrderPublic, OrderUpdateStatus

router = APIRouter()
logger = logging.getLogger(__name__)


def _calc_total(items: list[dict]) -> float:
    return float(sum(item["price"] * item["quantity"] for item in items))


@router.post("/orders/", response_model=OrderPublic, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderPublic:
    items = [item.model_dump() for item in payload.items]
    order = Order(
        user_id=current_user.id,
        items=items,
        total_price=_calc_total(items),
        status=OrderStatus.PENDING,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    payload_out = OrderPublic.model_validate(order, from_attributes=True).model_dump(mode="json")
    try:
        redis = get_redis()
        await cache_set_order(redis, order.id, payload_out)
    except Exception as exc:
        logger.debug("Failed to cache order %s: %s", order.id, exc)
        pass
    try:
        await publisher.publish_json({"type": "new_order", "order_id": str(order.id), "user_id": order.user_id})
    except Exception as exc:
        logger.warning("Failed to publish new_order event (order_id=%s): %s", order.id, exc)
    return OrderPublic.model_validate(payload_out)


@router.get("/orders/{order_id}/", response_model=OrderPublic)
async def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderPublic:
    try:
        redis = get_redis()
        cached = await cache_get_order(redis, order_id)
        if cached is not None:
            if cached.get("user_id") != current_user.id:
                raise HTTPException(status_code=403, detail="Forbidden")
            return OrderPublic.model_validate(cached)
    except Exception as exc:
        logger.debug("Cache read failed for order %s: %s", order_id, exc)
        pass

    order = await db.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    payload = OrderPublic.model_validate(order, from_attributes=True).model_dump(mode="json")
    try:
        redis = get_redis()
        await cache_set_order(redis, order_id, payload)
    except Exception as exc:
        logger.debug("Cache write failed for order %s: %s", order_id, exc)
        pass
    return OrderPublic.model_validate(payload)


@router.patch("/orders/{order_id}/", response_model=OrderPublic)
async def update_order_status(
    order_id: uuid.UUID,
    payload: OrderUpdateStatus,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderPublic:
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    order.status = payload.status
    db.add(order)
    await db.commit()
    await db.refresh(order)
    payload_out = OrderPublic.model_validate(order, from_attributes=True).model_dump(mode="json")
    try:
        redis = get_redis()
        await cache_set_order(redis, order_id, payload_out)
    except Exception as exc:
        logger.debug("Cache write failed for order %s: %s", order_id, exc)
        pass
    return OrderPublic.model_validate(payload_out)


@router.get("/orders/user/{user_id}/", response_model=list[OrderPublic])
async def list_user_orders(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderPublic]:
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    orders = (
        await db.scalars(select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()))
    ).all()
    return [OrderPublic.model_validate(order, from_attributes=True) for order in orders]
