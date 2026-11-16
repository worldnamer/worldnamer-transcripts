import logging

from app.main import MAX_BODY_BYTES, MAX_TEXT_BYTES

TOO_LONG = {"outcome": "failed", "reason": "too_long"}


def test_text_over_the_limit_is_422_too_long_with_no_call(client, summarizer):
    response = client.post("/summary", json={"text": "a" * (MAX_TEXT_BYTES + 1)})
    assert response.status_code == 422
    assert response.json() == TOO_LONG
    assert summarizer.calls == []


def test_text_at_the_limit_is_accepted_and_sent_whole(client, summarizer):
    text = "a" * MAX_TEXT_BYTES
    response = client.post("/summary", json={"text": text})
    assert response.status_code == 200
    assert summarizer.calls == [text]


def test_the_limit_counts_utf8_bytes_not_characters(client, summarizer):
    # 100,000 three-byte characters is 300,000 bytes; one more character goes over.
    at_limit = "€" * (MAX_TEXT_BYTES // 3)
    assert client.post("/summary", json={"text": at_limit}).status_code == 200
    over = client.post("/summary", json={"text": at_limit + "€"})
    assert over.status_code == 422
    assert over.json() == TOO_LONG
    assert len(summarizer.calls) == 1


def test_oversize_content_length_is_refused_before_the_body_is_parsed(client, summarizer):
    # The body is not valid JSON: had it been parsed, the answer would be invalid_text.
    response = client.post(
        "/summary",
        content=b"{" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == TOO_LONG
    assert summarizer.calls == []


def test_oversize_content_length_without_a_token_is_still_401(client, summarizer):
    client.headers.pop("Authorization")
    response = client.post(
        "/summary", content=b"x" * (MAX_BODY_BYTES + 1), headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 401


def test_oversize_content_length_on_transcript_is_not_special_cased(client, fetcher):
    response = client.post(
        "/transcript",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.json() == {"error": "invalid_video_id"}


def test_lone_surrogate_is_invalid_text_not_a_crash(client, summarizer):
    response = client.post(
        "/summary",
        content=b'{"text": "broken \\ud800 text"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_text"}
    assert summarizer.calls == []


def test_too_long_is_logged_with_its_length_and_no_text(client, summarizer, caplog):
    text = "secret-marker-123" + "a" * MAX_TEXT_BYTES
    with caplog.at_level(logging.INFO, logger="transcripts"):
        client.post("/summary", json={"text": text})
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("summary")]
    assert "reason=too_long" in line
    assert f"bytes_in={len(text.encode())}" in line
    assert "secret-marker" not in line
