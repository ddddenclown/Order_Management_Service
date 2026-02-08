# Order Management Service (FastAPI)
# СМОТРИТЕ TEST_REPORT.md

Сервис управления заказами: FastAPI + PostgreSQL (SQLAlchemy/Alembic) + Redis (кеш и rate limit + Celery broker) + RabbitMQ (event-bus) + Celery (фоновые задачи).

## Запуск (Docker Compose)

1) Скопируй `.env.example` -> `.env` и при необходимости поправь значения.

2) Запусти:
```bash
docker compose up --build
```

API будет доступен на `http://localhost:8000`, Swagger UI: `http://localhost:8000/docs`.

RabbitMQ UI: `http://localhost:15672` (логин/пароль по умолчанию `guest/guest`).

## API

### Auth
- `POST /register/` — регистрация (email, password)
- `POST /token/` — получение JWT (OAuth2 Password Flow; `username` = email)

### Orders (только авторизованные)
- `POST /orders/` — создание заказа (публикует событие `new_order` в RabbitMQ)
- `GET /orders/{order_id}/` — получение заказа (read-through Redis cache, TTL 5 минут)
- `PATCH /orders/{order_id}/` — обновление статуса заказа (и обновляет кеш)
- `GET /orders/user/{user_id}/` — список заказов пользователя

## Фоновая обработка

Отдельный процесс `event-consumer` читает очередь `new_order` в RabbitMQ и запускает Celery task `process_order`.
Задача делает `sleep(2)` и печатает `Order {order_id} processed`.

