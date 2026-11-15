import pytest

VALID_ID = "6MbLd7DWnSE"


def test_ok_returns_lines(client, fetcher):
    fetcher.result = [{"text": "hi", "start": 0.0}, {"text": "there", "start": 1.5}]
    response = client.post("/transcript", json={"video_id": VALID_ID})
    assert response.status_code == 200
    assert response.json() == {"outcome": "ok", "lines": fetcher.result}
    assert fetcher.calls == [VALID_ID]


def test_no_captions_when_fetcher_returns_no_lines(client, fetcher):
    fetcher.result = []
    response = client.post("/transcript", json={"video_id": VALID_ID})
    assert response.status_code == 200
    assert response.json() == {"outcome": "no_captions"}


def test_extra_keys_are_ignored(client, fetcher):
    response = client.post("/transcript", json={"video_id": VALID_ID, "extra": 1})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"video_id": "abc"},
        {"video_id": "a" * 12},
        {"video_id": "abcdefghij!"},
        {"video_id": "abcdefghij\n"},
        {"video_id": "../../etc/x"},
        {"video_id": 12345678901},
        {"video_id": None},
        {"video_id": ["a"] * 11},
        {},
        [],
        "text",
    ],
)
def test_bad_body_is_422_and_never_reaches_the_fetcher(client, fetcher, body):
    response = client.post("/transcript", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_video_id"}
    assert fetcher.calls == []


def test_non_json_body_is_422_without_echo(client, fetcher):
    response = client.post(
        "/transcript", content=b"not-json-secret", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_video_id"}
    assert "secret" not in response.text


def test_missing_body_is_422(client, fetcher):
    response = client.post("/transcript")
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_video_id"}
