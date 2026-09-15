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
| `INGEST_SOURCE` | no       | `itunes` (default) or `fixtures`. See [Run the ingestion](#run-the-ingestion).   |
| `ITUNES_TIMEOUT_SECONDS` | no | Per-request timeout against iTunes (default `10`).                        |
| `ARTWORK_WORKERS` | no     | Concurrent artwork downloads (default `8`).                                 |
| `ARTWORK_TIMEOUT_SECONDS` | no | Per-image download timeout (default `5`).                                |

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

If port 8000 is taken, pass `--port 8010` (or any free port) to uvicorn.

## Authentication

Every endpoint except `/health` requires the `X-API-Key` header with the value of `API_KEY`.
A missing or wrong key returns `401`:

```sh
curl -i http://localhost:8000/podcasts
# HTTP/1.1 401 Unauthorized
# {"error":{"code":"unauthenticated","message":"Missing or invalid API key"}}

curl -H "X-API-Key: $API_KEY" http://localhost:8000/podcasts
```

In `/docs`, click **Authorize** and paste the key once to try every endpoint from the browser.

## Endpoints

| method | path                   | auth | description                                              |
| ------ | ---------------------- | ---- | -------------------------------------------------------- |
| `GET`  | `/health`              | no   | Liveness check.                                          |
| `POST` | `/ingest/bulk`         | yes  | Fetch the rock & roll batch from iTunes and store it.    |
| `POST` | `/ingest/{source_id}`  | yes  | Ingest one podcast by its iTunes `collectionId`.         |
| `GET`  | `/podcasts`            | yes  | Paginated catalogue listing with filters.                |
| `GET`  | `/podcasts/{id}`       | yes  | One podcast by its own `id` (not the iTunes id).         |

`GET /podcasts` query parameters:

| parameter | type   | default | description                                                    |
| --------- | ------ | ------- | -------------------------------------------------------------- |
| `genre`   | string | –       | Exact match, case-insensitive (e.g. `music`).                  |
| `country` | string | –       | Exact match, case-insensitive (e.g. `usa`).                    |
| `q`       | string | –       | Case-insensitive substring search over `title` and `author`.   |
| `limit`   | int    | `20`    | Page size, between 1 and 100.                                  |
| `offset`  | int    | `0`     | Number of rows to skip.                                        |

The response carries the page plus the total number of matches, so clients can compute the
number of pages:

```json
{ "items": [ { "id": 1, "source_id": 1001, "title": "...", "...": "..." } ], "total": 3, "limit": 20, "offset": 0 }
```

Results are ordered by `title`, then `id`, so pages are stable between requests.

## Run the ingestion

The catalogue starts empty. Fill it with one request (no body needed):

```sh
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/ingest/bulk
```

This queries the iTunes Search API for seven terms (`rock`, `rock and roll`, `classic rock`,
`punk rock`, `hard rock`, `metal`, `indie rock`), merges the results, stores them and
downloads every cover image to extract a colour palette. It takes around 15 seconds on the
first run and returns a summary:

```json
{
  "fetched": 527,
  "stored": 492,
  "updated": 0,
  "skipped": 35,
  "skipped_reasons": { "duplicate": 35 }
}
```

- `fetched` is the number of raw records received across all terms.
- `stored` and `updated` are new and existing podcasts (matched by iTunes id).
- `skipped` records are counted by reason: `duplicate` (same podcast under several
  terms), `missing_title`, `missing_author`, `missing_source_id`, `invalid_<field>`.
- `fetched == stored + updated + skipped` always holds.

The ingestion is idempotent: run it again and every podcast is updated in place
(`stored: 0`). Skipped records are also logged with their reason.

To ingest a single podcast, pass its iTunes `collectionId`:

```sh
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/ingest/1187775077
```

An unknown id returns `404`. If iTunes is unreachable after the retries, both endpoints
return `502`.

### Without network access

Set `INGEST_SOURCE=fixtures` in `.env` (and restart the API) to replay the iTunes responses
stored under `tests/fixtures/itunes/` instead of calling the live API. The same two endpoints
work unchanged; the fixtures contain 261 records (248 unique podcasts). Artwork is still
downloaded from the URLs in the fixtures; when that fails, the podcast is stored with
`color_palette: null`.

## Errors

Every error response, whatever raised it, has the same shape:

```json
{ "error": { "code": "not_found", "message": "Podcast 999 not found" } }
```

| status | code               | when                                             |
| ------ | ------------------ | ------------------------------------------------ |
| `401`  | `unauthenticated`  | Missing or wrong `X-API-Key`.                    |
| `404`  | `not_found`        | Unknown podcast id or unknown route.             |
| `405`  | `method_not_allowed` | Wrong HTTP method on an existing route.        |
| `422`  | `validation_error` | Invalid query/path parameter or body. `error.details` lists the offending fields. |
| `502`  | `upstream_error`   | The iTunes API failed during ingestion (after retries). |

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
