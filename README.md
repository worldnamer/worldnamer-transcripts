# worldnamer-transcripts

A small Python service that fetches a YouTube video's transcript for my personal website, [worldnamer.com](https://worldnamer.com).

FastAPI on uvicorn.

## Setup

Requires Python 3.12.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Run

```sh
.venv/bin/uvicorn app.main:app --port 8000
curl localhost:8000/health   # {"status":"ok"}
```

Run a single uvicorn process (no `--workers`).

## Test

```sh
.venv/bin/pytest
```

## Lint

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .   # drop --check to apply formatting
```
