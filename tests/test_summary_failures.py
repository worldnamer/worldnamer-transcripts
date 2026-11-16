import json
import logging

import pytest
import requests

from app.settings import Settings
from app.summarizer import MAX_RESPONSE_BYTES, SummaryFailed, make_summarizer
from tests.conftest import FAKE_DEEPINFRA_KEY, FakePost, FakeResponse, completion

SETTINGS = Settings(
    token="t" * 64,
    proxy_username="fake-user",
    proxy_password="fake-pass",
    deepinfra_key=FAKE_DEEPINFRA_KEY,
)
TEXT = "secret-marker-123 and more text"


def reason_for(post):
    with pytest.raises(SummaryFailed) as failure:
        make_summarizer(SETTINGS, post=post)(TEXT)
    return failure.value


def post_returning(status_code=200, **kwargs):
    post = FakePost()
    post.response = FakeResponse(status_code, **kwargs)
    return post


@pytest.mark.parametrize("status", [401, 403])
def test_our_key_rejected_is_unauthorized(status):
    failure = reason_for(post_returning(status, body={"error": "bad key"}))
    assert (failure.reason, failure.upstream_status) == ("unauthorized", status)


def test_429_is_rate_limited():
    failure = reason_for(post_returning(429, body={"error": "slow down"}))
    assert (failure.reason, failure.upstream_status) == ("rate_limited", 429)


@pytest.mark.parametrize("status", [500, 502, 503, 400, 404, 422, 301])
def test_other_statuses_are_service_error(status):
    failure = reason_for(post_returning(status, body={"error": "x"}))
    assert (failure.reason, failure.upstream_status) == ("service_error", status)


@pytest.mark.parametrize(
    "error",
    [requests.exceptions.ConnectionError("boom"), requests.exceptions.ChunkedEncodingError("x")],
)
def test_connection_failures_are_service_error(error):
    post = FakePost()
    post.error = error
    failure = reason_for(post)
    assert failure.reason == "service_error"
    assert failure.error_class is None


@pytest.mark.parametrize(
    "error", [requests.exceptions.ReadTimeout("slow"), requests.exceptions.ConnectTimeout("slow")]
)
def test_timeouts_are_timed_out(error):
    post = FakePost()
    post.error = error
    assert reason_for(post).reason == "timed_out"


def test_unknown_exception_is_service_error_with_its_class():
    post = FakePost()
    post.error = RuntimeError("detail with secret-marker-123")
    failure = reason_for(post)
    assert (failure.reason, failure.error_class) == ("service_error", "RuntimeError")


@pytest.mark.parametrize(
    "content",
    [b"not json at all", b"", b"[]", b'{"choices": [{"message": 5}], "usage": {}}'],
)
def test_bad_json_or_shape_is_service_error(content):
    failure = reason_for(post_returning(content=content))
    assert failure.reason == "service_error"
    assert failure.upstream_status == 200


def test_missing_or_odd_usage_is_service_error():
    body = completion()
    del body["usage"]
    assert reason_for(post_returning(body=body)).reason == "service_error"
    body = completion()
    body["usage"] = {"prompt_tokens": "many", "completion_tokens": 1}
    assert reason_for(post_returning(body=body)).reason == "service_error"


def test_response_over_one_megabyte_is_service_error():
    content = json.dumps(completion(content="x" * MAX_RESPONSE_BYTES)).encode()
    assert len(content) > MAX_RESPONSE_BYTES
    assert reason_for(post_returning(content=content)).reason == "service_error"


@pytest.mark.parametrize(
    "body",
    [
        {**completion(), "choices": []},
        {k: v for k, v in completion().items() if k != "choices"},
        completion(content=""),
        completion(content="  \n "),
        completion(content=None),
        completion(finish_reason="length"),
    ],
    ids=["empty-choices", "no-choices", "empty", "blank", "null", "cut-off"],
)
def test_no_usable_answer_is_empty_answer(body):
    failure = reason_for(post_returning(body=body))
    assert (failure.reason, failure.upstream_status) == ("empty_answer", 200)


def test_failure_carries_no_upstream_text_or_key():
    body = {"error": f"echo {TEXT} {FAKE_DEEPINFRA_KEY}"}
    failure = reason_for(post_returning(500, body=body))
    assert TEXT not in str(failure) and FAKE_DEEPINFRA_KEY not in str(failure)
    assert "secret-marker" not in repr(failure.__dict__)


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("unauthorized", 502),
        ("rate_limited", 502),
        ("service_error", 502),
        ("timed_out", 502),
        ("empty_answer", 502),
    ],
)
def test_route_answers_502_with_the_reason(client, summarizer, reason, status):
    summarizer.error = SummaryFailed(reason, 500)
    response = client.post("/summary", json={"text": TEXT})
    assert response.status_code == status
    assert response.json() == {"outcome": "failed", "reason": reason}


def test_route_never_echoes_text_or_key_on_failure(client, summarizer):
    summarizer.error = RuntimeError(f"{TEXT} {FAKE_DEEPINFRA_KEY}")
    response = client.post("/summary", json={"text": TEXT})
    assert response.status_code == 502
    assert response.json() == {"outcome": "failed", "reason": "service_error"}
    assert "secret-marker" not in response.text
    assert FAKE_DEEPINFRA_KEY not in response.text


def test_unknown_class_is_logged_by_name_only(client, summarizer, caplog):
    summarizer.error = RuntimeError(f"{TEXT} {FAKE_DEEPINFRA_KEY}")
    with caplog.at_level(logging.INFO, logger="transcripts"):
        client.post("/summary", json={"text": TEXT})
    log = " ".join(r.getMessage() for r in caplog.records)
    assert "outcome=failed reason=service_error" in log
    assert "error_class=RuntimeError" in log
    assert "secret-marker" not in log
    assert FAKE_DEEPINFRA_KEY not in log


def test_failure_log_line_has_reason_status_and_no_text(client, summarizer, caplog):
    summarizer.error = SummaryFailed("rate_limited", 429)
    with caplog.at_level(logging.INFO, logger="transcripts"):
        client.post("/summary", json={"text": TEXT})
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("summary")]
    assert "outcome=failed reason=rate_limited" in line
    assert f"bytes_in={len(TEXT.encode())}" in line
    assert "upstream_status=429" in line
    assert "secret-marker" not in line
