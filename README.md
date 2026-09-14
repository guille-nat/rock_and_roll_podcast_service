# Rock & Roll Podcast Service

REST API for a catalogue of rock & roll podcasts ingested from the iTunes Search API.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — manages the Python interpreter, dependencies and
  virtual environment. Install it with:

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  uv downloads the pinned Python version (see `.python-version`) automatically.

## Environment variables

Copy the example file and fill in the values:

```sh
cp .env.example .env
```

| variable       | required | description                                              |
| -------------- | -------- | -------------------------------------------------------- |
| `API_KEY`      | yes      | Shared secret expected in the `X-API-Key` header.        |
| `DATABASE_URL` | yes      | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/db`. |

The service refuses to start if either is missing or empty.

## Install dependencies

```sh
uv sync
```

## Run the API

```sh
uv run uvicorn app.main:app --reload
```

- Health check: <http://localhost:8000/health>
- OpenAPI docs: <http://localhost:8000/docs>

## Run the tests

```sh
uv run pytest
```
