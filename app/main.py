import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, StringConstraints

from app.fetcher import Fetcher, make_fetcher
from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Refuses to start (non-zero exit) when configuration is missing; no network call here.
    app.state.settings = Settings.from_env(os.environ)
    yield


# Generated API docs are switched off so the service reveals nothing about itself.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

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
    lines = fetcher(body.video_id)
    if not lines:
        return JSONResponse({"outcome": "no_captions"})
    return JSONResponse({"outcome": "ok", "lines": lines})
