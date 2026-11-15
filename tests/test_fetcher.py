from types import SimpleNamespace

import pytest
import requests
from youtube_transcript_api import NoTranscriptFound

from app import fetcher as fetcher_module
from app.settings import Settings

SETTINGS = Settings(token="t" * 64, proxy_username="fake-user", proxy_password="fake-pass")


class FakeTranscript:
    def __init__(self, language_code, texts):
        self.language_code = language_code
        self.texts = texts

    def fetch(self):
        return SimpleNamespace(
            snippets=[SimpleNamespace(text=t, start=float(i)) for i, t in enumerate(self.texts)]
        )


class FakeList:
    def __init__(self, transcripts):
        self.transcripts = transcripts

    def find_transcript(self, codes):
        for t in self.transcripts:
            if t.language_code in codes:
                return t
        raise NoTranscriptFound("x", codes, None)

    def __iter__(self):
        return iter(self.transcripts)


@pytest.fixture
def library(monkeypatch):
    created = []

    class FakeApi:
        listing = FakeList([])
        error = None

        def __init__(self, **kwargs):
            created.append(kwargs)

        def list(self, video_id):
            if FakeApi.error:
                raise FakeApi.error
            return FakeApi.listing

    monkeypatch.setattr(fetcher_module, "YouTubeTranscriptApi", FakeApi)
    FakeApi.created = created
    return FakeApi


def run():
    return fetcher_module.make_fetcher(SETTINGS)("6MbLd7DWnSE")


def test_prefers_english(library):
    library.listing = FakeList([FakeTranscript("de", ["hallo"]), FakeTranscript("en", ["hello"])])
    assert run() == [{"text": "hello", "start": 0.0}]


def test_falls_back_to_first_listed(library):
    library.listing = FakeList([FakeTranscript("de", ["hallo"]), FakeTranscript("fr", ["salut"])])
    assert run() == [{"text": "hallo", "start": 0.0}]


def test_empty_listing_is_no_captions(library):
    library.listing = FakeList([])
    assert run() == []


def test_zero_snippets_is_no_captions(library):
    library.listing = FakeList([FakeTranscript("en", [])])
    assert run() == []


def test_new_client_is_built_per_call_with_proxy_and_timeout_session(library):
    library.listing = FakeList([])
    fetch = fetcher_module.make_fetcher(SETTINGS)
    fetch("6MbLd7DWnSE")
    fetch("6MbLd7DWnSE")
    assert len(library.created) == 2
    kwargs = library.created[0]
    assert isinstance(kwargs["http_client"], fetcher_module.TimeoutSession)
    assert kwargs["proxy_config"].retries_when_blocked == 2


def test_timeout_session_sets_default_timeout(monkeypatch):
    seen = {}

    def fake_request(self, method, url, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(requests.Session, "request", fake_request)
    fetcher_module.TimeoutSession().request("GET", "http://example.invalid")
    assert seen["timeout"] == (5, 10)
    fetcher_module.TimeoutSession().request("GET", "http://example.invalid", timeout=1)
    assert seen["timeout"] == 1
