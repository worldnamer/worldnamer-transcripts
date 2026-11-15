def test_health_returns_ok_status_only(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_token(client):
    client.headers.pop("Authorization")
    assert client.get("/health").status_code == 200


def test_generated_docs_are_not_served(client):
    # With the token the docs routes do not exist; without it they are refused first.
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
        client.headers.pop("Authorization", None)
        assert client.get(path).status_code == 401
        client.headers["Authorization"] = "Bearer " + "t" * 64
