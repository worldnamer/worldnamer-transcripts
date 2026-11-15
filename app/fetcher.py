"""The only module that calls youtube-transcript-api."""

from collections.abc import Callable
from urllib.parse import quote

import requests
from youtube_transcript_api import NoTranscriptFound, YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from app.settings import Settings

Line = dict[str, str | float]
# Takes a video id and returns its transcript lines; an empty list means no captions.
Fetcher = Callable[[str], list[Line]]

# (connect, read) seconds. Bounds every request the library makes through the session.
REQUEST_TIMEOUT = (5, 10)
# Extra tries the library makes through the proxy when YouTube blocks an exit address.
RETRIES_WHEN_BLOCKED = 2
PROXY_HOST = "p.webshare.io"
PROXY_PORT = 80


class ProxyConfig(GenericProxyConfig):
    """The Webshare proxy with the login sent exactly as given.

    The library's own Webshare config appends a "-rotate" suffix to the username, which is wrong
    for a login that already selects its exit by itself.
    """

    def __init__(self, username: str, password: str):
        login = f"{quote(username, safe='')}:{quote(password, safe='')}"
        url = f"http://{login}@{PROXY_HOST}:{PROXY_PORT}/"
        super().__init__(http_url=url, https_url=url)

    @property
    def prevent_keeping_connections_alive(self) -> bool:
        # A kept-alive connection would keep the same exit address across retries.
        return True

    @property
    def retries_when_blocked(self) -> int:
        return RETRIES_WHEN_BLOCKED


class TimeoutSession(requests.Session):
    """A session that applies a default timeout, since the library sets none."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return super().request(method, url, **kwargs)


def make_fetcher(settings: Settings) -> Fetcher:
    def fetch(video_id: str) -> list[Line]:
        # A new client per call: the library's client is not thread-safe.
        api = YouTubeTranscriptApi(
            proxy_config=ProxyConfig(settings.proxy_username, settings.proxy_password),
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
