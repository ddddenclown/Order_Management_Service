from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


@dataclass
class _Counter:
    count: int
    reset_at: float


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._mem: dict[str, _Counter] = {}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in {"/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        key = f"rl:{client}:{path}"
        now = time.time()

        redis_decision = await self._allow_redis(key)
        if redis_decision is True:
            return await call_next(request)
        if redis_decision is False:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

        if self._allow_memory(key, now):
            return await call_next(request)

        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )

    async def _allow_redis(self, key: str) -> bool | None:
        try:
            redis = get_redis()
            count = await asyncio.wait_for(redis.incr(key), timeout=settings.redis_socket_timeout_seconds)
            if count == 1:
                await asyncio.wait_for(
                    redis.expire(key, settings.rate_limit_seconds),
                    timeout=settings.redis_socket_timeout_seconds,
                )
            return count <= settings.rate_limit_times
        except Exception as exc:
            logger.debug("Rate limiter redis unavailable, falling back to memory: %s", exc)
            return None

    def _allow_memory(self, key: str, now: float) -> bool:
        counter = self._mem.get(key)
        if counter is None or now >= counter.reset_at:
            self._mem[key] = _Counter(count=1, reset_at=now + settings.rate_limit_seconds)
            return True
        if counter.count >= settings.rate_limit_times:
            return False
        counter.count += 1
        return True
