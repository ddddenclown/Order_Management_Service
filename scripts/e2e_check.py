from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
import urllib.request
from urllib.parse import urlencode


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


def _req_json(method: str, path: str, data: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    url = f"{BASE_URL}{path}"
    body = None if data is None else json.dumps(data).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8")
    except Exception as exc:
        if hasattr(exc, "code"):
            return exc.code, exc.read().decode("utf-8")
        raise


def _wait_ok(path: str, timeout_s: float = 40.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Service did not become ready at {BASE_URL}{path}")


def main() -> int:
    _wait_ok("/docs")

    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123!"

    status, body = _req_json("POST", "/register/", {"email": email, "password": password})
    assert status == 201, (status, body)

    form = urlencode({"username": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/token/",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        token_payload = json.loads(resp.read().decode("utf-8"))
    token = token_payload["access_token"]

    auth = {"Authorization": f"Bearer {token}"}

    status, body = _req_json(
        "POST",
        "/orders/",
        {"items": [{"sku": "ABC", "quantity": 2, "price": 10.5}]},
        headers=auth,
    )
    assert status == 201, (status, body)
    order = json.loads(body)
    order_id = order["id"]

    status, _ = _req_json("GET", f"/orders/{order_id}/", headers=auth)
    assert status == 200, status
    status, _ = _req_json("GET", f"/orders/{order_id}/", headers=auth)
    assert status == 200, status

    status, body = _req_json("PATCH", f"/orders/{order_id}/", {"status": "PAID"}, headers=auth)
    assert status == 200, (status, body)

    redis_container = subprocess.check_output(["docker", "compose", "ps", "-q", "redis"], text=True).strip()
    if not redis_container:
        raise RuntimeError("Redis container not found (docker compose ps -q redis is empty)")
    cached = subprocess.check_output(
        ["docker", "exec", redis_container, "redis-cli", "GET", f"orders:{order_id}"],
        text=True,
    ).strip()
    assert cached, "Expected order to be cached in Redis"

    ttl_raw = subprocess.check_output(
        ["docker", "exec", redis_container, "redis-cli", "TTL", f"orders:{order_id}"],
        text=True,
    ).strip()
    ttl = int(ttl_raw)
    assert ttl <= 300 and ttl > 0, f"Unexpected TTL: {ttl}"

    codes = []
    for _i in range(0, 20):
        st, _ = _req_json("GET", f"/orders/{order_id}/", headers=auth)
        codes.append(st)
    assert 429 in codes, f"Expected some 429 responses, got: {codes}"

    time.sleep(3)
    logs = subprocess.check_output(
        ["docker", "compose", "logs", "--no-color", "--tail=200", "celery-worker"],
        text=True,
    )
    if not re.search(rf"Order {re.escape(order_id)} processed", logs):
        raise AssertionError("Expected celery-worker logs to contain processed message")

    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
