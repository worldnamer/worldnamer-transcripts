from collections.abc import Mapping
from dataclasses import dataclass, field

TOKEN_VAR = "TRANSCRIPTS_TOKEN"
PROXY_USER_VAR = "WEBSHARE_PROXY_USERNAME"
PROXY_PASSWORD_VAR = "WEBSHARE_PROXY_PASSWORD"
DEEPINFRA_KEY_VAR = "DEEPINFRA_API_KEY"
DEEPINFRA_MODEL_VAR = "DEEPINFRA_MODEL"
DEEPINFRA_BASE_URL_VAR = "DEEPINFRA_BASE_URL"
DEFAULT_MODEL = "zai-org/GLM-5.3-Flash"
DEFAULT_BASE_URL = "https://api.deepinfra.com/v1/openai"
MIN_TOKEN_LENGTH = 32


class SettingsError(Exception):
    """Startup configuration is unusable. The message names variables, never values."""


@dataclass(frozen=True)
class Settings:
    # Secret fields are excluded from repr so a logged settings object cannot leak them.
    token: str = field(repr=False)
    proxy_username: str = field(repr=False)
    proxy_password: str = field(repr=False)
    deepinfra_key: str = field(repr=False)
    deepinfra_model: str = DEFAULT_MODEL
    deepinfra_base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        missing = [
            name
            for name in (TOKEN_VAR, PROXY_USER_VAR, PROXY_PASSWORD_VAR, DEEPINFRA_KEY_VAR)
            if not environ.get(name)
        ]
        if missing:
            raise SettingsError("missing or empty environment variables: " + ", ".join(missing))
        token = environ[TOKEN_VAR]
        if len(token) < MIN_TOKEN_LENGTH:
            raise SettingsError(f"{TOKEN_VAR} is shorter than {MIN_TOKEN_LENGTH} characters")
        # The key is sent to this address, so it must be encrypted in transit. Only the
        # presence of the key is checked here, never its validity, so a wrong key cannot
        # make the service crash-loop.
        base_url = environ.get(DEEPINFRA_BASE_URL_VAR) or DEFAULT_BASE_URL
        if not base_url.startswith("https://"):
            raise SettingsError(f"{DEEPINFRA_BASE_URL_VAR} must start with https://")
        return cls(
            token=token,
            proxy_username=environ[PROXY_USER_VAR],
            proxy_password=environ[PROXY_PASSWORD_VAR],
            deepinfra_key=environ[DEEPINFRA_KEY_VAR],
            deepinfra_model=environ.get(DEEPINFRA_MODEL_VAR) or DEFAULT_MODEL,
            deepinfra_base_url=base_url.rstrip("/"),
        )
