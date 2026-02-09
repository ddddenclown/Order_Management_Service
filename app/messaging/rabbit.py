from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika

from app.core.config import settings

logger = logging.getLogger(__name__)


class RabbitPublisher:
    def __init__(self, url: str, queue_name: str) -> None:
        self._url = url
        self._queue_name = queue_name
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        self._connection = await asyncio.wait_for(
            aio_pika.connect_robust(self._url),
            timeout=settings.rabbitmq_connect_timeout_seconds,
        )
        self._channel = await self._connection.channel()
        await self._channel.declare_queue(self._queue_name, durable=True)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._channel = None

    async def publish_json(self, message: dict[str, Any]) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                await self.connect()
                assert self._channel is not None
                body = json.dumps(message).encode("utf-8")
                msg = aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                )
                await asyncio.wait_for(
                    self._channel.default_exchange.publish(msg, routing_key=self._queue_name),
                    timeout=settings.rabbitmq_publish_timeout_seconds,
                )
                return
            except Exception as exc:
                last_exc = exc
                logger.warning("RabbitMQ publish failed (attempt=%s): %s", attempt, exc)
                await self.close()
                await asyncio.sleep(0.2 * (2 ** (attempt - 1)))
        assert last_exc is not None
        raise last_exc


publisher = RabbitPublisher(url=settings.rabbitmq_url, queue_name=settings.rabbitmq_queue_new_order)
