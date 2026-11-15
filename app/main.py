from fastapi import FastAPI

# Generated API docs are switched off so the service reveals nothing about itself.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    # No credentials: the hosting platform probes this, and it returns only the status.
    return {"status": "ok"}
