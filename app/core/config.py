from __future__ import annotations

import secrets

from pydantic import PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_env: str = "local"
    secret_key: str = ""
    access_token_exp_minutes: int = 60
    algorithm: str = "HS256"

    database_url: str = "sqlite+pysqlite:///./dev.db"
    cors_allow_origins_raw: str = ""

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue_new_order: str = "new_order"

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"

    rate_limit_times: int = 10
    rate_limit_seconds: int = 60

    _generated_secret_key: str | None = PrivateAttr(default=None)

    @property
    def cors_allow_origins(self) -> list[str]:
        raw = self.cors_allow_origins_raw.strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def jwt_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        if self._generated_secret_key is None:
            self._generated_secret_key = secrets.token_urlsafe(32)
            print("WARNING: SECRET_KEY not set; using an ephemeral key (tokens will reset on restart).")
        return self._generated_secret_key


settings = Settings()
