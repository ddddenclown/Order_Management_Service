from __future__ import annotations

import asyncio
import json

import aio_pika

from app.core.config import settings
from app.worker.tasks import process_order


async def main() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(settings.rabbitmq_queue_new_order, durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    payload = json.loads(message.body.decode("utf-8"))
                    order_id = payload.get("order_id")
                    if isinstance(order_id, str) and order_id:
                        process_order.delay(order_id)


if __name__ == "__main__":
    asyncio.run(main())

