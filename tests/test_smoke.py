from fastapi.testclient import TestClient

from app.main import app


def test_docs_available() -> None:
    client = TestClient(app)
    r = client.get("/docs")
    assert r.status_code == 200

