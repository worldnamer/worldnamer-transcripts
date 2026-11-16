import json
import logging

import pytest

from tests.conftest import FAKE_DEEPINFRA_KEY, FAKE_TOKEN

TEXT = "The quick brown fox jumps over the lazy dog, secret-marker-123."


def test_ok_returns_summary_model_and_counts(client, summarizer):
    response = client.post("/summary", json={"text": TEXT})
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "ok",
        "summary": "A short summary.",
        "model": "vendor/model-x",
        "tokens_in": 120,
        "tokens_out": 45,
    }


def test_text_reaches_the_summarizer_unchanged(client, summarizer):
    text = "  leading and trailing  \n\nand an inner line\n  "
    client.post("/summary", json={"text": text})
    assert summarizer.calls == [text]


def test_extra_keys_are_ignored(client, summarizer):
    assert client.post("/summary", json={"text": TEXT, "extra": 1}).status_code == 200


@pytest.mark.parametrize(
    "body",
    [{}, {"text": ""}, {"text": "   \n\t "}, {"text": None}, {"text": 5}, {"text": ["a"]}, [], "x"],
)
def test_invalid_body_is_422_invalid_text_and_makes_no_call(client, summarizer, body):
    response = client.post("/summary", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_text"}
    assert summarizer.calls == []


def test_non_json_body_is_422_without_echo(client, summarizer):
    response = client.post(
        "/summary", content=b"not-json-secret", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_text"}
    assert "secret" not in response.text


def test_transcript_still_answers_invalid_video_id(client, fetcher):
    response = client.post("/transcript", json={"video_id": "abc"})
    assert response.json() == {"error": "invalid_video_id"}


def test_no_token_is_401_and_makes_no_call(client, summarizer):
    client.headers.pop("Authorization")
    response = client.post("/summary", json={"text": TEXT})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert summarizer.calls == []


def test_wrong_token_is_401_and_makes_no_call(client, summarizer):
    response = client.post(
        "/summary", json={"text": TEXT}, headers={"Authorization": "Bearer " + FAKE_TOKEN[:-1]}
    )
    assert response.status_code == 401
    assert summarizer.calls == []


def test_unauthenticated_malformed_body_is_401_not_422(client, summarizer):
    client.headers.pop("Authorization")
    response = client.post(
        "/summary", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401


def test_log_line_has_lengths_and_no_text(client, summarizer, caplog):
    text = "héllo secret-marker-123"
    with caplog.at_level(logging.INFO, logger="transcripts"):
        client.post("/summary", json={"text": text})
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("summary")]
    assert f"bytes_in={len(text.encode())}" in line
    assert "tokens_in=120" in line and "tokens_out=45" in line
    assert "upstream_status=200" in line
    assert "duration_ms=" in line
    assert "secret-marker-123" not in line
    assert "A short summary." not in line


def test_response_never_contains_the_key(client, summarizer):
    response = client.post("/summary", json={"text": TEXT})
    assert FAKE_DEEPINFRA_KEY not in response.text
    assert FAKE_DEEPINFRA_KEY not in json.dumps(dict(response.headers))
