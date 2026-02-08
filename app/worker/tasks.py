from __future__ import annotations

import time
import uuid

from app.worker.celery_app import celery_app


@celery_app.task(name="process_order")
def process_order(order_id: str) -> None:
    time.sleep(2)
    _ = uuid.UUID(order_id)
    print(f"Order {order_id} processed")

