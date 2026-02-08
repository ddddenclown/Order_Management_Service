from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "orders_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)
