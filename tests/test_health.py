from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok_status_only():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generated_docs_are_not_served():
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
