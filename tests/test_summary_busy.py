import threading

import pytest

from app import main
from app.main import MAX_TEXT_BYTES
from app.summarizer import SummaryFailed
from tests.conftest import FakeFetcher, FakeSummarizer

TEXT = "some text"
VID = "6MbLd7DWnSE"


class Gate:
    """A stand-in that holds its call open until released, so another call can arrive meanwhile."""

    def __init__(self, result):
        self.started = threading.Event()
        self.release = threading.Event()
        self.result = result

    def __call__(self, argument):
        self.started.set()
        assert self.release.wait(timeout=5)
        return self.result


@pytest.fixture
def slow_summary(client):
    gate = Gate(FakeSummarizer().result)
    client.app.dependency_overrides[main.get_summarizer] = lambda: gate
    yield gate
    gate.release.set()
    client.app.dependency_overrides.clear()


def start_in_thread(call):
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(response=call()))
    worker.start()
    return worker, holder


def test_second_summary_during_a_summary_is_429_busy(client, slow_summary):
    worker, first = start_in_thread(lambda: client.post("/summary", json={"text": TEXT}))
    assert slow_summary.started.wait(timeout=5)

    second = client.post("/summary", json={"text": TEXT})
    assert second.status_code == 429
    assert second.json() == {"error": "busy"}

    slow_summary.release.set()
    worker.join(timeout=5)
    assert first["response"].status_code == 200


def test_a_running_fetch_does_not_make_a_summary_busy(client, summarizer):
    assert main.fetch_lock.acquire(blocking=False)
    try:
        assert client.post("/summary", json={"text": TEXT}).status_code == 200
    finally:
        main.fetch_lock.release()


def test_a_running_summary_does_not_make_a_fetch_busy(client, slow_summary):
    fetcher = FakeFetcher()
    client.app.dependency_overrides[main.get_fetcher] = lambda: fetcher
    worker, _ = start_in_thread(lambda: client.post("/summary", json={"text": TEXT}))
    assert slow_summary.started.wait(timeout=5)

    assert client.post("/transcript", json={"video_id": VID}).status_code == 200
    slow_summary.release.set()
    worker.join(timeout=5)


def test_refused_calls_take_no_lock(client, slow_summary):
    worker, _ = start_in_thread(lambda: client.post("/summary", json={"text": TEXT}))
    assert slow_summary.started.wait(timeout=5)

    unauthorized = client.post(
        "/summary", json={"text": TEXT}, headers={"Authorization": "Bearer nope"}
    )
    assert unauthorized.status_code == 401
    assert client.post("/summary", json={"text": "  "}).json() == {"error": "invalid_text"}
    too_long = client.post("/summary", json={"text": "a" * (MAX_TEXT_BYTES + 1)})
    assert too_long.json() == {"outcome": "failed", "reason": "too_long"}
    slow_summary.release.set()
    worker.join(timeout=5)


def test_refused_calls_leave_the_lock_free(client, summarizer):
    client.post("/summary", json={"text": ""})
    client.post("/summary", json={"text": "a" * (MAX_TEXT_BYTES + 1)})
    assert not main.summary_lock.locked()


def test_lock_is_released_after_success_and_after_failure(client, summarizer):
    summarizer.error = SummaryFailed("service_error")
    assert client.post("/summary", json={"text": TEXT}).status_code == 502
    assert not main.summary_lock.locked()
    summarizer.error = RuntimeError("x")
    assert client.post("/summary", json={"text": TEXT}).status_code == 502
    assert not main.summary_lock.locked()
    summarizer.error = None
    assert client.post("/summary", json={"text": TEXT}).status_code == 200
    assert not main.summary_lock.locked()
