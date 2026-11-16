import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings, SettingsError

GOOD = {
    "TRANSCRIPTS_TOKEN": "a" * 32,
    "WEBSHARE_PROXY_USERNAME": "fake-user",
    "WEBSHARE_PROXY_PASSWORD": "fake-pass",
    "DEEPINFRA_API_KEY": "fake-deepinfra-key",
}


def test_from_env_reads_every_required_value():
    settings = Settings.from_env(GOOD)
    assert settings.token == "a" * 32
    assert settings.proxy_username == "fake-user"
    assert settings.proxy_password == "fake-pass"
    assert settings.deepinfra_key == "fake-deepinfra-key"


@pytest.mark.parametrize("name", sorted(GOOD))
@pytest.mark.parametrize("blank", ["missing", "empty"])
def test_from_env_rejects_missing_or_empty_variable_naming_it(name, blank):
    environ = dict(GOOD)
    if blank == "missing":
        del environ[name]
    else:
        environ[name] = ""
    with pytest.raises(SettingsError) as error:
        Settings.from_env(environ)
    assert name in str(error.value)


def test_from_env_rejects_short_token_without_echoing_it():
    environ = dict(GOOD, TRANSCRIPTS_TOKEN="short-secret-value")
    with pytest.raises(SettingsError) as error:
        Settings.from_env(environ)
    assert "TRANSCRIPTS_TOKEN" in str(error.value)
    assert "short-secret-value" not in str(error.value)


def test_error_never_contains_other_values():
    environ = dict(GOOD, WEBSHARE_PROXY_PASSWORD="")
    with pytest.raises(SettingsError) as error:
        Settings.from_env(environ)
    assert "fake-user" not in str(error.value)
    assert "a" * 32 not in str(error.value)


def test_repr_hides_secrets():
    text = repr(Settings.from_env(GOOD))
    assert "fake-user" not in text
    assert "fake-pass" not in text
    assert "a" * 32 not in text
    assert "fake-deepinfra-key" not in text


def test_model_and_base_url_have_defaults():
    settings = Settings.from_env(GOOD)
    assert settings.deepinfra_model == "zai-org/GLM-5.3-Flash"
    assert settings.deepinfra_base_url == "https://api.deepinfra.com/v1/openai"


def test_environment_overrides_model_and_base_url():
    environ = dict(
        GOOD,
        DEEPINFRA_MODEL="other/model",
        DEEPINFRA_BASE_URL="https://example.test/v1/openai/",
    )
    settings = Settings.from_env(environ)
    assert settings.deepinfra_model == "other/model"
    assert settings.deepinfra_base_url == "https://example.test/v1/openai"


@pytest.mark.parametrize("url", ["http://api.example.test/v1", "ftp://x.test", "example.test"])
def test_non_https_base_url_is_refused_without_echoing_it(url):
    with pytest.raises(SettingsError) as error:
        Settings.from_env(dict(GOOD, DEEPINFRA_BASE_URL=url))
    assert "DEEPINFRA_BASE_URL" in str(error.value)
    assert url not in str(error.value)


def test_app_refuses_to_start_without_configuration():
    with pytest.raises(SettingsError), TestClient(app):
        pass


def test_app_keeps_settings_on_state(client):
    assert client.app.state.settings.proxy_username == "fake-proxy-user"
