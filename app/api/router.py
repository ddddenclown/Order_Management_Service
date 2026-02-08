from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, orders

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(orders.router, tags=["orders"])

