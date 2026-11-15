"""Maps what the library and requests raise to the service's closed set of outcomes."""

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

NO_CAPTIONS = "no_captions"
REASONS = frozenset(
    {"blocked", "timed_out", "unavailable", "proxy_refused", "youtube_error", "unknown"}
)

_RULES: tuple[tuple[tuple[type[BaseException], ...], str], ...] = (
    # Timeout first: a connect timeout is also a ConnectionError.
    ((requests.exceptions.Timeout,), "timed_out"),
    # A wrong proxy login comes back as a 407 and surfaces as a ProxyError.
    ((requests.exceptions.ProxyError,), "proxy_refused"),
    ((TranscriptsDisabled, NoTranscriptFound), NO_CAPTIONS),
    ((VideoUnavailable, VideoUnplayable, InvalidVideoId, AgeRestricted), "unavailable"),
    # IpBlocked is a RequestBlocked; listed for clarity.
    ((RequestBlocked, IpBlocked, PoTokenRequired), "blocked"),
    ((YouTubeRequestFailed, YouTubeDataUnparsable, FailedToCreateConsentCookie), "youtube_error"),
)


def classify(error: BaseException) -> str:
    """Return NO_CAPTIONS or one reason from REASONS. Never inspects the error's text."""
    for types, outcome in _RULES:
        if isinstance(error, types):
            return outcome
    return "unknown"
