# Rock & Roll Podcast Service

REST API for a catalogue of rock & roll podcasts ingested from the iTunes Search API.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — manages the Python interpreter, dependencies and
  virtual environment. Install it with:

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  uv downloads the pinned Python version (see `.python-version`) automatically.
- [Docker](https://docs.docker.com/get-docker/) with Compose, to run PostgreSQL locally.

## Environment variables

Copy the example file and fill in the values:

```sh
cp .env.example .env
```

| variable        | required | description                                                                 |
| --------------- | -------- | --------------------------------------------------------------------------- |
| `API_KEY`       | yes      | Shared secret expected in the `X-API-Key` header.                           |
| `DATABASE_URL`  | yes      | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/db`.         |
| `POSTGRES_PORT` | no       | Host port published by the Compose database (default `5432`). Keep it in sync with `DATABASE_URL`. |

The service refuses to start if `API_KEY` or `DATABASE_URL` is missing or empty.

## Install dependencies

```sh
uv sync
```

## Start the database

```sh
docker compose up -d --wait db
```

This starts PostgreSQL 18 with the credentials from `.env.example` (local development only)
and creates two databases on first start: `podcasts` for the API and `podcasts_test` for the
test suite. If port 5432 is already in use on your machine, set `POSTGRES_PORT` in `.env` and
use the same port in `DATABASE_URL`.

## Apply migrations

The schema is managed with Alembic; the application never creates tables by itself.

```sh
uv run alembic upgrade head
```

## Run the API

```sh
uv run uvicorn app.main:app --reload
```

- Health check: <http://localhost:8000/health>
- OpenAPI docs: <http://localhost:8000/docs>

## Run the tests

The tests need the Compose database running. They use the same server as `DATABASE_URL`
but the `podcasts_test` database, which they migrate up before the run and back down
afterwards, so development data is never touched.

```sh
uv run pytest
```

## Type checking

The whole codebase, tests and migrations included, is checked with mypy in strict mode:

```sh
uv run mypy
```
