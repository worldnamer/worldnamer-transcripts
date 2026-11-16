import json

from app.settings import Settings
from app.summarizer import MAX_TOKENS, REQUEST_TIMEOUT, make_summarizer
from tests.conftest import FakePost, FakeResponse, completion

SETTINGS = Settings(
    token="t" * 64,
    proxy_username="fake-user",
    proxy_password="fake-pass",
    deepinfra_key="fake-deepinfra-key",
    deepinfra_model="vendor/configured",
    deepinfra_base_url="https://llm.example.test/v1/openai",
)
TEXT = "  The text, exactly as given.\n\nSecond paragraph.  "


def test_returns_summary_model_and_token_counts():
    post = FakePost()
    summary = make_summarizer(SETTINGS, post=post)(TEXT)
    assert summary.text == "A short summary."
    assert summary.model == "vendor/model-x"
    assert (summary.tokens_in, summary.tokens_out) == (120, 45)
    assert summary.upstream_status == 200


def test_request_shape():
    post = FakePost()
    make_summarizer(SETTINGS, post=post)(TEXT)
    (call,) = post.calls
    assert call["url"] == "https://llm.example.test/v1/openai/chat/completions"
    assert call["headers"] == {"Authorization": "Bearer fake-deepinfra-key"}
    assert call["timeout"] == REQUEST_TIMEOUT == (5, 150)
    assert call["json"]["model"] == "vendor/configured"
    assert call["json"]["max_tokens"] == MAX_TOKENS == 4096


def test_text_is_sent_unchanged_as_the_user_message():
    post = FakePost()
    make_summarizer(SETTINGS, post=post)(TEXT)
    system, user = post.calls[0]["json"]["messages"]
    assert system["role"] == "system"
    assert user == {"role": "user", "content": TEXT}


def test_prompt_asks_for_plain_english_prose_and_treats_text_as_material():
    post = FakePost()
    make_summarizer(SETTINGS, post=post)(TEXT)
    system = post.calls[0]["json"]["messages"][0]["content"]
    assert "plain English prose" in system
    assert "about 200 words" in system
    assert "not instructions" in system
    assert "fake-deepinfra-key" not in system


def test_key_is_only_in_the_authorization_header():
    post = FakePost()
    make_summarizer(SETTINGS, post=post)(TEXT)
    call = post.calls[0]
    assert "fake-deepinfra-key" not in json.dumps(call["json"])
    assert "fake-deepinfra-key" not in call["url"]


def test_model_falls_back_to_the_configured_one_when_the_response_names_none():
    post = FakePost()
    body = completion()
    del body["model"]
    post.response = FakeResponse(body=body)
    assert make_summarizer(SETTINGS, post=post)(TEXT).model == "vendor/configured"
