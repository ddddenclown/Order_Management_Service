# Отчет о запуске и проверке сервиса (Order Management Service)

Дата проверки: **2026-02-09**  
Окружение: **macOS**, Docker **29.1.3**, Docker Compose **v2.40.3-desktop.1**

## 1) Как запускалось

1. Подготовка env:
   - `.env.example` → `.env`
   - `SECRET_KEY` задан как случайная строка (не дефолтное значение).

2. Запуск инфраструктуры и приложения:
```bash
docker compose up -d --build
```

3. Прогон тестов:
```bash
docker compose run --rm api pytest -q
python3 scripts/e2e_check.py
```

Сервисы в `docker-compose.yml`:
- `api` (FastAPI + Alembic миграции при старте)
- `postgres`
- `redis`
- `rabbitmq`
- `event-consumer` (читает `new_order` из RabbitMQ)
- `celery-worker` (Celery worker, broker = Redis DB 1)

## 2) Проверка Swagger UI

Проверено:
- `GET /docs` → **200 OK**

## 3) Проверка сценария авторизации (JWT OAuth2 Password Flow)

### 3.1 Регистрация
Проверено:
- `POST /register/` (email, password) → **201 Created**

Ожидаемое поведение:
- создание пользователя
- обработка дублей email: **409**

### 3.2 Получение токена
Проверено:
- `POST /token/` (form-urlencoded, `username=email`) → **200 OK**
- в ответе: `access_token`, `token_type=bearer`

Ожидаемое поведение:
- неверный пароль → **401**

## 4) Проверка сценария заказов

### 4.1 Создание заказа (только авторизованные)
Проверено:
- `POST /orders/` (Bearer token) → **201 Created**
- в ответе: `id (UUID)`, `user_id`, `items`, `total_price`, `status=PENDING`, `created_at`

Дополнительно:
- после создания заказа публикуется событие `new_order` в RabbitMQ

### 4.2 Получение заказа (read-through Redis cache, TTL=5 минут)
Проверено:
- `GET /orders/{order_id}/` → **200 OK**
- повторный `GET /orders/{order_id}/` → **200 OK**

Проверка наличия записи в Redis (DB 0):
- ключ: `orders:{order_id}`
- значение: сериализованный JSON заказа

### 4.3 Обновление статуса и обновление кеша
Проверено:
- `PATCH /orders/{order_id}/` с `status=PAID` → **200 OK**
- после PATCH кеш обновляется (значение в `orders:{order_id}` содержит `status=PAID`)

### 4.4 Список заказов пользователя
Проверено:
- `GET /orders/user/{user_id}/` → **200 OK**
- доступ разрешен только владельцу (другому пользователю → **403**)

## 5) Проверка event-bus (RabbitMQ) + consumer + Celery

Бизнес-цепочка:
1) `api` публикует сообщение `new_order` в RabbitMQ при создании заказа  
2) `event-consumer` читает `new_order` и вызывает Celery task `process_order.delay(order_id)`  
3) `celery-worker` выполняет задачу: `sleep(2)` и печатает `Order {order_id} processed`

Фактическое подтверждение по логам `celery-worker`:
- задача `process_order` зарегистрирована
- задача принята и успешно выполнена ~ за 2 секунды
- в логах присутствует строка формата: `Order <uuid> processed`

## 6) Rate limiting

Проверено:
- при серии быстрых запросов к одному и тому же endpoint возвращается **429** после превышения лимита.

Параметры (env):
- `RATE_LIMIT_TIMES`
- `RATE_LIMIT_SECONDS`

## 7) Исправления, сделанные в ходе проверки

1) Alembic миграция: создание enum `order_status` было неидемпотентным (enum создавался дважды).  
   - Исправлено: используется `sqlalchemy.dialects.postgresql.ENUM(..., create_type=False)` и явное `create(checkfirst=True)`.

2) Alembic env: при запуске в контейнере не находился модуль `app`.  
   - Исправлено: добавлен `sys.path.append(<repo_root>)` в `alembic/env.py`.

3) Хеширование паролей: bcrypt backend конфликтовал с актуальной версией `bcrypt` и ломал регистрацию.  
   - Исправлено: переход на `argon2` (через `passlib[argon2]` + `argon2-cffi`).

4) Celery: worker не импортировал задачи, task считался “unregistered”.  
   - Исправлено: добавлен `include=["app.worker.tasks"]` в Celery app.

5) БД: исключено блокирование event loop из-за синхронной работы с БД внутри `async`-эндпоинтов.  
   - Исправлено: переход на `AsyncSession` (SQLAlchemy asyncio); приложение использует `asyncpg` (для PostgreSQL) и `aiosqlite` (для SQLite). Миграции Alembic по-прежнему используют `psycopg` через `DATABASE_URL`.

6) Интеграции: добавлены таймауты и ретраи для Redis/RabbitMQ, плюс логирование деградаций (без падения API на кеш/шину).  
   - Redis: `socket_connect_timeout`, `socket_timeout`, `retry_on_timeout`.
   - RabbitMQ: `connect/publish` с таймаутами и backoff retry.

7) Безопасность/конфиг: усилены проверки конфигурации.  
   - `SECRET_KEY` обязателен, если `APP_ENV` не `local`.
   - пароль при регистрации валидируется (минимальная длина).

## 8) Итог

Сервис поднимается через `docker compose`, Swagger UI доступен, эндпоинты из ТЗ работают, Redis кеш и rate limit работают, событие `new_order` реально проходит через RabbitMQ → consumer → Celery, задача выполняется в фоне. Автотесты (pytest + e2e check) проходят.
