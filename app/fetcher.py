"""The only module that calls youtube-transcript-api."""

from collections.abc import Callable

import requests
from youtube_transcript_api import NoTranscriptFound, YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.settings import Settings

Line = dict[str, str | float]
# Takes a video id and returns its transcript lines; an empty list means no captions.
Fetcher = Callable[[str], list[Line]]

# (connect, read) seconds. Bounds every request the library makes through the session.
REQUEST_TIMEOUT = (5, 10)
# Extra tries the library makes through the proxy when YouTube blocks an exit address.
RETRIES_WHEN_BLOCKED = 2


class TimeoutSession(requests.Session):
    """A session that applies a default timeout, since the library sets none."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return super().request(method, url, **kwargs)


def make_fetcher(settings: Settings) -> Fetcher:
    def fetch(video_id: str) -> list[Line]:
        # A new client per call: the library's client is not thread-safe.
        api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                settings.proxy_username,
                settings.proxy_password,
                retries_when_blocked=RETRIES_WHEN_BLOCKED,
            ),
            http_client=TimeoutSession(),
        )
        transcripts = api.list(video_id)
        chosen = _choose(transcripts)
        if chosen is None:
            return []
        return [{"text": s.text, "start": s.start} for s in chosen.fetch().snippets]

    return fetch


def _choose(transcripts):
    """English if there is one (manual before generated), else the first listed."""
    try:
        return transcripts.find_transcript(["en"])
    except NoTranscriptFound:
        pass
    return next(iter(transcripts), None)
