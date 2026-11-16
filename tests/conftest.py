import socket

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_fetcher

FAKE_TOKEN = "t" * 64
FAKE_PROXY_USERNAME = "fake-proxy-user"
FAKE_PROXY_PASSWORD = "fake-proxy-password"
FAKE_DEEPINFRA_KEY = "fake-deepinfra-key-0123456789"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "TRANSCRIPTS_TOKEN",
        "WEBSHARE_PROXY_USERNAME",
        "WEBSHARE_PROXY_PASSWORD",
        "DEEPINFRA_API_KEY",
        "DEEPINFRA_MODEL",
        "DEEPINFRA_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTS_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", FAKE_PROXY_USERNAME)
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", FAKE_PROXY_PASSWORD)
    monkeypatch.setenv("DEEPINFRA_API_KEY", FAKE_DEEPINFRA_KEY)
    with TestClient(app, headers={"Authorization": f"Bearer {FAKE_TOKEN}"}) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)


class FakeFetcher:
    """Stands in for the library wrapper; records calls and returns or raises a set result."""

    def __init__(self):
        self.result = [{"text": "hello", "start": 0.0}]
        self.error = None
        self.calls = []

    def __call__(self, video_id):
        self.calls.append(video_id)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def fetcher(client):
    fake = FakeFetcher()
    client.app.dependency_overrides[get_fetcher] = lambda: fake
    yield fake
    client.app.dependency_overrides.clear()
