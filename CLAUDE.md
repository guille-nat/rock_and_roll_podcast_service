# Rock & Roll Podcast Service

A small REST API for a catalog of rock & roll podcasts. Everything below is already
decided — do not re-litigate these choices, implement them.

## Language

All code, comments, docstrings, commit messages and documentation in **English**.
Conversation with the developer is in Spanish.

## Stack

- Python 3.12+
- **uv** for dependency and environment management
- FastAPI
- SQLAlchemy 2.0 with typed `Mapped[]` declarative models
- Alembic for migrations (never `create_all()`)
- PostgreSQL
- Pydantic v2 for request/response schemas
- httpx for outbound HTTP
- Pillow for image colour extraction
- pytest
- Docker Compose for local startup

Ask before adding any dependency that is not in this list.

### Dependency management with uv

- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
  **Both files are committed.** The lockfile pins the exact resolved versions so
  the reviewer gets the same environment from a clean checkout.
- Add dependencies with `uv add <package>` and dev-only ones with
  `uv add --dev <package>`. Never hand-edit `pyproject.toml` dependency lists
  and never generate a `requirements.txt`.
- Run everything through `uv run` — `uv run pytest`, `uv run alembic upgrade
head`, `uv run uvicorn app.main:app --reload`. Do not activate a virtualenv
  manually in documented commands.
- Pin the interpreter with a `.python-version` file.
- In the Dockerfile, copy `pyproject.toml` and `uv.lock` first and run
  `uv sync --frozen --no-dev` as its own layer, before copying the source, so
  the dependency layer stays cached across code changes. `--frozen` makes the
  build fail if the lockfile is out of date instead of silently re-resolving.
- The README must state uv as a prerequisite and include the one-line install
  command, since not every reviewer will have it.

### Libraries: do not reinvent solved problems

The rule above is about restraint, not about writing everything by hand. Order
of preference for any given problem:

1. The standard library, if it covers it.
2. A mature, widely used, actively maintained library.
3. Own code — only when the problem is genuinely specific to this service.

Hand-rolling something that a well-known library already does correctly is a
finding in review, not a sign of skill. This applies especially to anything
touching security, parsing untrusted input, or protocol details, where the
naive implementation is usually subtly wrong.

Concrete cases in this project:

- **Stripping HTML from descriptions** — never with regular expressions. HTML is
  not a regular language and a regex will mangle entities and leave fragments
  behind. Use a real parser or a sanitiser.
- **Credential comparison** — `secrets.compare_digest`, never a hand-written
  loop and never `==`.
- **Retries and backoff against iTunes** — use an established retry helper
  rather than a hand-written loop with `time.sleep`. Retry only on timeouts,
  connection errors and 5xx; never on 4xx.
- **Colour extraction** — Pillow's own quantiser, not a hand-written
  clustering algorithm.
- **Settings and validation** — Pydantic, not manual `os.environ` parsing and
  `if` chains.

Conversely, do not add a dependency for something the standard library or an
already-present library does in a few lines. A package for date formatting, for
string casing, or for wrapping an HTTP call is noise.

When a dependency is added, it must be: currently maintained, in common use,
and not pulling in a large transitive tree for a small feature. Record in
NOTES.md the ones where the choice was not obvious, with the one-line reason.

## Scope

### Must-have core (build this first, completely)

- `POST /ingest/bulk` — fetch a batch of rock & roll podcasts from iTunes,
  normalise and store them. Idempotent. Returns a summary.
- `POST /ingest/{source_id}` — ingest a single podcast on demand.
- Cover image download + colour palette extraction during both ingestion paths.
- `GET /podcasts` — pagination plus at least one filter/search.
- `GET /podcasts/{id}` — single podcast.
- `GET /podcasts/export` — streaming export of the entire catalogue.
- `GET /health` — public, unauthenticated.
- API key authentication on everything except `/health`.
- OpenAPI docs at `/docs`.
- Meaningful tests (see Testing).
- Startup guide in README.md.
- NOTES.md (see Deliverables).

### Non-goals — do NOT build these

No frontend or UI. No cloud deployment. No user registration or account
management. No API versioning — keep routes flat. No Celery, no Redis, no
message queue. No repository pattern, no service layer abstraction, no
dependency-injection container. Keep the layering shallow: router → small
module of business logic → SQLAlchemy.

### Nice-to-have

Only after the entire core is done and tested. Do not start any of these
without asking first.

## Data source

iTunes Search API. No API key required.

`https://itunes.apple.com/search?media=podcast&term=<term>&limit=200`

The endpoint returns at most 200 results and has **no offset parameter**, so a
"batch" is built by querying several terms and merging the results:

    rock, rock and roll, classic rock, punk rock, hard rock, metal, indie rock

That list is the working definition of "rock & roll" for this service. It is a
judgement call, it is documented, and it is consistent. That is all that is
required.

Store a small sample of raw iTunes responses under `tests/fixtures/` and make
ingestion able to read from them as a fallback, so the upstream source being
down never blocks the reviewer.

## Data model

Single table `podcasts`:

| column                      | notes                                                           |
| --------------------------- | --------------------------------------------------------------- |
| `id`                        | own primary key                                                 |
| `source_id`                 | iTunes `collectionId`, **UNIQUE** — this is the idempotency key |
| `title`                     | from `collectionName`                                           |
| `author`                    | from `artistName`                                               |
| `description`               | **nullable** — iTunes Search does not return it                 |
| `genre`                     | from `primaryGenreName`, filterable                             |
| `country`                   | filterable                                                      |
| `feed_url`                  | nullable                                                        |
| `artwork_url`               | nullable                                                        |
| `color_palette`             | JSON, nullable                                                  |
| `created_at` / `updated_at` |                                                                 |

`description` being nullable is a deliberate trade-off: fetching it would mean
pulling and parsing each podcast's RSS feed, which multiplies ingestion time.
Document this in NOTES.md.

## Ingestion rules

Flow: fetch across terms → de-duplicate by `source_id` in memory → for each
record: validate, normalise, upsert, then fetch artwork and extract palette.

**Idempotency lives in the database**, not in application code. Use PostgreSQL
`INSERT ... ON CONFLICT (source_id) DO UPDATE` via
`sqlalchemy.dialects.postgresql.insert`. Never do
`if exists: update else: insert` — that has a race condition under concurrent
requests.

**Normalisation**: strip HTML tags from text fields, trim whitespace, collapse
repeated spaces, coerce empty strings to `None`.

**Validation**: a record is skipped if it is missing `source_id`, `title` or
`author`. Skipping is never silent.

**Response shape**:

```json
{
  "fetched": 412,
  "stored": 180,
  "updated": 20,
  "skipped": 212,
  "skipped_reasons": { "duplicate": 208, "missing_title": 4 }
}
```

## Colour palette

Downloads run concurrently through a `ThreadPoolExecutor` with ~8 workers and a
short per-image timeout. This is I/O-bound, so threads are the right tool and a
task queue would be over-engineering at this scope.

Every download is individually guarded. **A failed or missing image stores the
podcast with `color_palette = None` and never aborts the ingestion.** This is an
explicit requirement of the brief.

Extract the palette with Pillow's `quantize()`. Store a handful of hex strings.

## Export endpoint

The brief says to assume the catalogue can be very large, so the export must
**never materialise the full result set in memory**.

- Format: NDJSON (one JSON object per line) — streams without having to close a
  JSON array.
- Serve through `StreamingResponse`.
- Iterate with `execution_options(yield_per=1000)` so the cursor stays
  server-side.
- **The database session must outlive the generator.** Do not close it in a
  FastAPI dependency that returns before streaming finishes — that is the
  classic failure mode of this pattern.

## Authentication

Static API key in the `X-API-Key` header, read from the `API_KEY` environment
variable at startup. Enforced as a FastAPI dependency on every router except
`/health`. Missing or wrong key returns **401**.

Compare with `secrets.compare_digest`, never `==` — string comparison
short-circuits and leaks timing information.

The key never goes in the repository. Ship a `.env.example` with the variable
name and no value.

Rationale, for NOTES.md: the service has no users, so there is no subject to
attribute permissions to. A JWT flow would end up validating against the same
shared secret with extra moving parts. Known limitations: rotating the key
requires a redeploy, and there is no per-client attribution; with multiple
consumers the next step would be a table of hashed keys with creation and
revocation timestamps.

## Errors

One global exception handler. Every error response has the same shape:

```json
{ "error": { "code": "not_found", "message": "Podcast 123 not found" } }
```

Status codes: 401 unauthenticated, 404 missing record, 422 invalid input,
502 upstream source failure.

## Code conventions

- Full type hints on every function signature. The brief explicitly asks for
  typed Python.
- Pydantic schemas separate from SQLAlchemy models.
- No bare `except Exception`. Catch the specific exception, and only where there
  is something meaningful to do about it.
- Small modules with obvious names. Prefer a correct small solution over a
  clever one.
- Configuration through environment variables via Pydantic Settings.

## Testing

Meaningful tests, not coverage for its own sake. The ones that matter:

1. Ingesting the same payload twice does not create duplicates.
2. A malformed record is skipped while the rest of the batch is stored.
3. A failing image download stores the podcast with a null palette.
4. A request without an API key returns 401.
5. Export streams without loading everything into memory.

Mock the iTunes calls with the stored fixtures — tests must not hit the network.

## Deliverables

Beyond the code, these are graded and must not be left for the last minute:

- **README.md** — startup guide: prerequisites, environment variables, how to
  start, how to run ingestion, how to run the tests. If a reviewer has to guess
  a step, it is not documented well enough.
- **NOTES.md** — decisions and assumptions (storage, auth, validation rules),
  trade-offs, what would be improved with more time, where AI tools were used,
  plus a short paragraph on how this service would evolve to ingest
  continuously and scale to millions of episodes.
- **Architecture overview** inside NOTES.md — a simple Mermaid or ASCII diagram
  of external source → ingestion → storage → API, plus a few sentences on the
  data model and request flow.
- **Deployment explanation** inside NOTES.md — where it would run, how storage
  and secrets would be handled, how a new version would ship. Nothing is
  actually deployed.

## Working style

- Commit in small, incremental steps with clear messages. The repository is
  public and the commit history is part of what is reviewed.
- Stop and ask before adding a dependency, an abstraction layer, or any feature
  outside the core list above.
- When something is ambiguous, state the assumption in NOTES.md rather than
  building for both cases.

