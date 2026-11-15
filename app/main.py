import hmac
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, StringConstraints

from app.fetcher import Fetcher, make_fetcher
from app.outcomes import NO_CAPTIONS, classify
from app.settings import Settings

logger = logging.getLogger("transcripts")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Refuses to start (non-zero exit) when configuration is missing; no network call here.
    app.state.settings = Settings.from_env(os.environ)
    yield


# Generated API docs are switched off so the service reveals nothing about itself.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

PUBLIC_PATHS = frozenset({"/health"})


def _token_matches(header: str | None, token: str) -> bool:
    if header is None:
        return False
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    # Constant-time comparison on bytes, so timing does not reveal how much of a guess matched.
    return hmac.compare_digest(presented.encode(), token.encode())


@app.middleware("http")
async def require_bearer_token(request: Request, call_next):
    # Deny by default. This is middleware, not a dependency, so a request is refused before
    # routing and body parsing (a dependency would let a malformed body answer 422 first).
    if request.url.path not in PUBLIC_PATHS and not _token_matches(
        request.headers.get("authorization"), request.app.state.settings.token
    ):
        return JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptRequest(BaseModel):
    # Strict: a number or null is rejected rather than coerced. Extra keys are ignored.
    video_id: Annotated[StrictStr, StringConstraints(pattern=VIDEO_ID_PATTERN.pattern)]


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Echoes nothing from the request: no input, no field names, no validator text.
    return JSONResponse({"error": "invalid_video_id"}, status_code=422)


def get_fetcher(request: Request) -> Fetcher:
    return make_fetcher(request.app.state.settings)


@app.get("/health")
def health() -> dict[str, str]:
    # No credentials: the hosting platform probes this, and it returns only the status.
    return {"status": "ok"}


@app.post("/transcript")
def transcript(
    body: TranscriptRequest, fetcher: Annotated[Fetcher, Depends(get_fetcher)]
) -> JSONResponse:
    started = time.monotonic()
    error_class = None
    reason = None
    try:
        lines = fetcher(body.video_id)
        outcome = "ok" if lines else NO_CAPTIONS
    except Exception as error:  # noqa: BLE001 - catch-all so nothing reaches the server's tracebacks
        # Only the class name is kept. The error text can carry the proxy login (requests
        # builds http://user:pass@host), so it is never logged or returned.
        classified = classify(error)
        if classified == NO_CAPTIONS:
            outcome = NO_CAPTIONS
        else:
            outcome, reason = "failed", classified
            if classified == "unknown":
                error_class = type(error).__name__
    duration_ms = round((time.monotonic() - started) * 1000)
    line = f"outcome={outcome} reason={reason} video_id={body.video_id} duration_ms={duration_ms}"
    if error_class:
        line += f" error_class={error_class}"
    logger.info(line)

    if outcome == "ok":
        return JSONResponse({"outcome": "ok", "lines": lines})
    if outcome == NO_CAPTIONS:
        return JSONResponse({"outcome": NO_CAPTIONS})
    return JSONResponse({"outcome": "failed", "reason": reason}, status_code=502)
