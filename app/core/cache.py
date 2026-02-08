from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis


ORDER_CACHE_TTL_SECONDS = 300


def order_cache_key(order_id: uuid.UUID) -> str:
    return f"orders:{order_id}"


async def cache_get_order(redis: Redis, order_id: uuid.UUID) -> dict[str, Any] | None:
    raw = await redis.get(order_cache_key(order_id))
    if not raw:
        return None
    return json.loads(raw)


async def cache_set_order(redis: Redis, order_id: uuid.UUID, payload: dict[str, Any]) -> None:
    await redis.set(order_cache_key(order_id), json.dumps(payload), ex=ORDER_CACHE_TTL_SECONDS)

