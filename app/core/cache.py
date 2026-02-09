from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from redis.asyncio import Redis


ORDER_CACHE_TTL_SECONDS = 300


def order_cache_key(order_id: uuid.UUID) -> str:
    return f"orders:{order_id}"


async def cache_get_order(redis: Redis, order_id: uuid.UUID) -> dict[str, Any] | None:
    raw = await asyncio.wait_for(redis.get(order_cache_key(order_id)), timeout=2.0)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set_order(redis: Redis, order_id: uuid.UUID, payload: dict[str, Any]) -> None:
    await asyncio.wait_for(
        redis.set(order_cache_key(order_id), json.dumps(payload), ex=ORDER_CACHE_TTL_SECONDS),
        timeout=2.0,
    )
