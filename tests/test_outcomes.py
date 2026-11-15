import logging

import pytest
import requests
from youtube_transcript_api import (
    AgeRestricted,
    FailedToCreateConsentCookie,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)

from app.outcomes import classify

VID = "6MbLd7DWnSE"


def build(cls):
    if cls is NoTranscriptFound:
        return cls(VID, ["en"], None)
    if cls is YouTubeRequestFailed:
        return cls(VID, "boom")
    if cls is VideoUnplayable:
        return cls(VID, "reason", [])
    return cls(VID)


@pytest.mark.parametrize(
    ("cls", "expected"),
    [
        (TranscriptsDisabled, "no_captions"),
        (NoTranscriptFound, "no_captions"),
        (VideoUnavailable, "unavailable"),
        (VideoUnplayable, "unavailable"),
        (InvalidVideoId, "unavailable"),
        (AgeRestricted, "unavailable"),
        (RequestBlocked, "blocked"),
        (IpBlocked, "blocked"),
        (PoTokenRequired, "blocked"),
        (YouTubeRequestFailed, "youtube_error"),
        (YouTubeDataUnparsable, "youtube_error"),
        (FailedToCreateConsentCookie, "youtube_error"),
    ],
)
def test_library_errors_map_to_outcomes(cls, expected):
    assert classify(build(cls)) == expected


def test_timeouts_map_to_timed_out_even_when_also_connection_errors():
    assert classify(requests.exceptions.ReadTimeout()) == "timed_out"
    assert classify(requests.exceptions.ConnectTimeout()) == "timed_out"


def test_proxy_error_maps_to_proxy_refused():
    assert classify(requests.exceptions.ProxyError()) == "proxy_refused"


def test_anything_else_is_unknown():
    assert classify(ValueError("x")) == "unknown"
    assert classify(requests.exceptions.ConnectionError()) == "unknown"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RequestBlocked(VID), "blocked"),
        (requests.exceptions.ReadTimeout(), "timed_out"),
        (VideoUnavailable(VID), "unavailable"),
        (requests.exceptions.ProxyError(), "proxy_refused"),
        (YouTubeDataUnparsable(VID), "youtube_error"),
        (RuntimeError("x"), "unknown"),
    ],
)
def test_route_reports_failure_with_fixed_reason(client, fetcher, error, reason):
    fetcher.error = error
    response = client.post("/transcript", json={"video_id": VID})
    assert response.status_code == 502
    assert response.json() == {"outcome": "failed", "reason": reason}


def test_library_no_captions_errors_are_200(client, fetcher):
    fetcher.error = TranscriptsDisabled(VID)
    response = client.post("/transcript", json={"video_id": VID})
    assert response.status_code == 200
    assert response.json() == {"outcome": "no_captions"}


def test_response_and_log_never_carry_exception_text(client, fetcher, caplog):
    secret = "http://fake-proxy-user:fake-proxy-password@p.webshare.io"
    fetcher.error = RuntimeError(secret)
    with caplog.at_level(logging.DEBUG):
        response = client.post("/transcript", json={"video_id": VID})
    assert secret not in response.text
    assert "fake-proxy-password" not in response.text
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "fake-proxy-password" not in logged
    assert secret not in logged
    assert all(record.exc_info is None for record in caplog.records)


def test_one_info_line_per_call_with_class_name_only_for_unknown(client, fetcher, caplog):
    with caplog.at_level(logging.INFO, logger="transcripts"):
        client.post("/transcript", json={"video_id": VID})
        fetcher.error = RuntimeError("secret")
        client.post("/transcript", json={"video_id": VID})
        fetcher.error = RequestBlocked(VID)
        client.post("/transcript", json={"video_id": VID})
    messages = [r.getMessage() for r in caplog.records if r.name == "transcripts"]
    assert len(messages) == 3
    assert messages[0].startswith("outcome=ok reason=None video_id=" + VID)
    assert "duration_ms=" in messages[0]
    assert "outcome=failed reason=unknown" in messages[1]
    assert "error_class=RuntimeError" in messages[1]
    assert "error_class" not in messages[2]
    assert not any("secret" in m for m in messages)
