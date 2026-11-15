from collections.abc import Mapping
from dataclasses import dataclass, field

TOKEN_VAR = "TRANSCRIPTS_TOKEN"
PROXY_USER_VAR = "WEBSHARE_PROXY_USERNAME"
PROXY_PASSWORD_VAR = "WEBSHARE_PROXY_PASSWORD"
MIN_TOKEN_LENGTH = 32


class SettingsError(Exception):
    """Startup configuration is unusable. The message names variables, never values."""


@dataclass(frozen=True)
class Settings:
    # Secret fields are excluded from repr so a logged settings object cannot leak them.
    token: str = field(repr=False)
    proxy_username: str = field(repr=False)
    proxy_password: str = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        missing = [
            name
            for name in (TOKEN_VAR, PROXY_USER_VAR, PROXY_PASSWORD_VAR)
            if not environ.get(name)
        ]
        if missing:
            raise SettingsError("missing or empty environment variables: " + ", ".join(missing))
        token = environ[TOKEN_VAR]
        if len(token) < MIN_TOKEN_LENGTH:
            raise SettingsError(f"{TOKEN_VAR} is shorter than {MIN_TOKEN_LENGTH} characters")
        return cls(
            token=token,
            proxy_username=environ[PROXY_USER_VAR],
            proxy_password=environ[PROXY_PASSWORD_VAR],
        )
