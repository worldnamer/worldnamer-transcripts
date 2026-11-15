import pytest
from fastapi.testclient import TestClient

from app.main import app

FAKE_TOKEN = "t" * 64
FAKE_PROXY_USERNAME = "fake-proxy-user"
FAKE_PROXY_PASSWORD = "fake-proxy-password"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("TRANSCRIPTS_TOKEN", "WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTS_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", FAKE_PROXY_USERNAME)
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", FAKE_PROXY_PASSWORD)
    with TestClient(app) as test_client:
        yield test_client
