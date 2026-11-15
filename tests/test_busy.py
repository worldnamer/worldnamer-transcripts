import threading

import pytest

from app import main

VID = "6MbLd7DWnSE"


@pytest.fixture
def slow_fetch(client):
    """A fetcher that holds the lock until released, so a second call can arrive meanwhile."""
    started = threading.Event()
    release = threading.Event()

    def slow(video_id):
        started.set()
        assert release.wait(timeout=5)
        return [{"text": "hi", "start": 0.0}]

    client.app.dependency_overrides[main.get_fetcher] = lambda: slow
    yield started, release
    release.set()
    client.app.dependency_overrides.clear()


def test_second_call_during_a_fetch_is_429_busy(client, slow_fetch):
    started, release = slow_fetch
    first = {}
    worker = threading.Thread(
        target=lambda: first.update(response=client.post("/transcript", json={"video_id": VID}))
    )
    worker.start()
    assert started.wait(timeout=5)

    second = client.post("/transcript", json={"video_id": VID})
    assert second.status_code == 429
    assert second.json() == {"error": "busy"}

    release.set()
    worker.join(timeout=5)
    assert first["response"].status_code == 200


def test_unauthenticated_and_invalid_calls_do_not_take_the_lock(client, slow_fetch):
    started, release = slow_fetch
    worker = threading.Thread(target=lambda: client.post("/transcript", json={"video_id": VID}))
    worker.start()
    assert started.wait(timeout=5)

    bad = client.post(
        "/transcript", json={"video_id": VID}, headers={"Authorization": "Bearer nope"}
    )
    assert bad.status_code == 401
    assert client.post("/transcript", json={"video_id": "abc"}).status_code == 422
    release.set()
    worker.join(timeout=5)


def test_lock_is_released_after_success_and_after_failure(client, fetcher):
    fetcher.error = RuntimeError("x")
    assert client.post("/transcript", json={"video_id": VID}).status_code == 502
    fetcher.error = None
    assert client.post("/transcript", json={"video_id": VID}).status_code == 200
    assert not main.fetch_lock.locked()
