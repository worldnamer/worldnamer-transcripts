import hmac
import logging
import os
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, StringConstraints, field_validator

from app.fetcher import Fetcher, make_fetcher
from app.outcomes import NO_CAPTIONS, classify
from app.settings import Settings
from app.summarizer import Summarizer, SummaryFailed, make_summarizer

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

# The model's context is large (the reference model takes a million tokens), so this is a
# guard against absurd input rather than a fit to the context. 300,000 UTF-8 bytes is at most
# about 100,000 tokens. A longer text is refused whole; it is never cut.
MAX_TEXT_BYTES = 300_000
# Refuses a body before it is read. Generous: JSON escaping can make a text several times its size.
MAX_BODY_BYTES = 2_000_000

TOO_LONG = {"outcome": "failed", "reason": "too_long"}


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
    if request.url.path == "/summary" and _declared_length(request) > MAX_BODY_BYTES:
        return JSONResponse(TOO_LONG, status_code=422)
    return await call_next(request)


def _declared_length(request: Request) -> int:
    try:
        return int(request.headers.get("content-length", "0"))
    except ValueError:
        return 0


# One fetch at a time bounds memory, proxy spend and worst-case time.
fetch_lock = threading.Lock()

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptRequest(BaseModel):
    # Strict: a number or null is rejected rather than coerced. Extra keys are ignored.
    video_id: Annotated[StrictStr, StringConstraints(pattern=VIDEO_ID_PATTERN.pattern)]


class SummaryRequest(BaseModel):
    # Strict: a number or null is rejected rather than coerced. Extra keys are ignored.
    text: StrictStr

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank")
        try:
            value.encode()
        except UnicodeEncodeError:
            # A lone surrogate (JSON allows one) cannot be sent on as UTF-8.
            raise ValueError("not UTF-8") from None
        return value


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Echoes nothing from the request: no input, no field names, no validator text.
    code = "invalid_text" if request.url.path == "/summary" else "invalid_video_id"
    return JSONResponse({"error": code}, status_code=422)


def get_fetcher(request: Request) -> Fetcher:
    return make_fetcher(request.app.state.settings)


def get_summarizer(request: Request) -> Summarizer:
    return make_summarizer(request.app.state.settings)


@app.get("/health")
def health() -> dict[str, str]:
    # No credentials: the hosting platform probes this, and it returns only the status.
    return {"status": "ok"}


@app.post("/transcript")
def transcript(
    body: TranscriptRequest, fetcher: Annotated[Fetcher, Depends(get_fetcher)]
) -> JSONResponse:
    # Non-blocking: a second caller is told to retry later rather than queued behind a fetch
    # that can take over a minute.
    if not fetch_lock.acquire(blocking=False):
        return JSONResponse({"error": "busy"}, status_code=429)
    try:
        return _run_fetch(body.video_id, fetcher)
    finally:
        fetch_lock.release()


def _run_fetch(video_id: str, fetcher: Fetcher) -> JSONResponse:
    started = time.monotonic()
    error_class = None
    reason = None
    try:
        lines = fetcher(video_id)
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
    line = f"outcome={outcome} reason={reason} video_id={video_id} duration_ms={duration_ms}"
    if error_class:
        line += f" error_class={error_class}"
    logger.info(line)

    if outcome == "ok":
        return JSONResponse({"outcome": "ok", "lines": lines})
    if outcome == NO_CAPTIONS:
        return JSONResponse({"outcome": NO_CAPTIONS})
    return JSONResponse({"outcome": "failed", "reason": reason}, status_code=502)


@app.post("/summary")
def summary(
    body: SummaryRequest, summarizer: Annotated[Summarizer, Depends(get_summarizer)]
) -> JSONResponse:
    if len(body.text.encode()) > MAX_TEXT_BYTES:
        _log_summary("failed", "too_long", body.text, None, None, 0)
        return JSONResponse(TOO_LONG, status_code=422)
    return _run_summary(body.text, summarizer)


def _run_summary(text: str, summarizer: Summarizer) -> JSONResponse:
    started = time.monotonic()
    result = None
    reason = upstream_status = error_class = None
    try:
        result = summarizer(text)
        upstream_status = result.upstream_status
    except SummaryFailed as failure:
        reason, upstream_status, error_class = (
            failure.reason,
            failure.upstream_status,
            failure.error_class,
        )
    except Exception as error:  # noqa: BLE001 - catch-all so nothing reaches the server's tracebacks
        # Only the class name is kept: error text can carry the request, and so the text.
        reason, error_class = "service_error", type(error).__name__
    duration_ms = round((time.monotonic() - started) * 1000)
    outcome = "ok" if result else "failed"
    _log_summary(outcome, reason, text, result, upstream_status, duration_ms, error_class)

    if result is None:
        return JSONResponse({"outcome": "failed", "reason": reason}, status_code=502)
    return JSONResponse(
        {
            "outcome": "ok",
            "summary": result.text,
            "model": result.model,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
        }
    )


def _log_summary(outcome, reason, text, result, upstream_status, duration_ms, error_class=None):
    # Lengths and counts only: neither the text nor the summary is ever logged.
    line = (
        f"summary outcome={outcome} reason={reason} bytes_in={len(text.encode())} "
        f"tokens_in={result.tokens_in if result else None} "
        f"tokens_out={result.tokens_out if result else None} "
        f"upstream_status={upstream_status} duration_ms={duration_ms}"
    )
    if error_class:
        line += f" error_class={error_class}"
    logger.info(line)
