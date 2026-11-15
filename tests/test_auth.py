import pytest

from tests.conftest import FAKE_TOKEN

UNAUTHORIZED = {"error": "unauthorized"}


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_token_is_401(client, fetcher):
    client.headers.pop("Authorization")
    assert_unauthorized(client.post("/transcript", json={"video_id": "6MbLd7DWnSE"}))
    assert fetcher.calls == []


@pytest.mark.parametrize(
    "header",
    [
        "Bearer wrong-token",
        "Bearer " + FAKE_TOKEN[:-1],
        "Bearer " + FAKE_TOKEN + "x",
        "Bearer",
        "Bearer ",
        FAKE_TOKEN,
        "Basic " + FAKE_TOKEN,
        "Token " + FAKE_TOKEN,
        "Bearer  " + FAKE_TOKEN,
    ],
)
def test_wrong_token_is_401_same_as_missing(client, fetcher, header):
    response = client.post(
        "/transcript", json={"video_id": "6MbLd7DWnSE"}, headers={"Authorization": header}
    )
    assert_unauthorized(response)
    assert fetcher.calls == []


def test_scheme_is_case_insensitive(client, fetcher):
    for scheme in ("bearer", "BEARER", "BeArEr"):
        response = client.post(
            "/transcript",
            json={"video_id": "6MbLd7DWnSE"},
            headers={"Authorization": f"{scheme} {FAKE_TOKEN}"},
        )
        assert response.status_code == 200


def test_unauthenticated_malformed_body_is_401_not_422(client, fetcher):
    client.headers.pop("Authorization")
    response = client.post(
        "/transcript", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert_unauthorized(response)


def test_unknown_path_is_401_without_token_and_404_with(client):
    assert client.get("/nope").status_code == 404
    client.headers.pop("Authorization")
    assert_unauthorized(client.get("/nope"))


def test_wrong_method_without_token_is_401(client):
    client.headers.pop("Authorization")
    assert_unauthorized(client.get("/transcript"))


def test_non_ascii_header_is_401_not_a_crash(client):
    response = client.get("/nope", headers={"Authorization": "Bearer café".encode("latin-1")})
    assert_unauthorized(response)
