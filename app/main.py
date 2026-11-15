import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Refuses to start (non-zero exit) when configuration is missing; no network call here.
    app.state.settings = Settings.from_env(os.environ)
    yield


# Generated API docs are switched off so the service reveals nothing about itself.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    # No credentials: the hosting platform probes this, and it returns only the status.
    return {"status": "ok"}
