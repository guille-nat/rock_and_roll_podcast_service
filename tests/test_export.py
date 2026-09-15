import json
from collections.abc import Iterator
from contextlib import nullcontext
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, insert
from sqlalchemy.orm import Session

from app.catalogue import iter_podcasts
from app.db import get_session_factory
from app.main import app
from app.models import Podcast
from app.schemas import PodcastOut


def _insert_rows(db_session: Session, count: int) -> None:
    db_session.execute(
        insert(Podcast),
        [{"source_id": i, "title": f"Podcast {i:05d}", "author": "A"} for i in range(1, count + 1)],
    )
    db_session.flush()


@pytest.fixture
def export_client(client: TestClient, db_session: Session) -> TestClient:
    """The export opens its own session; hand it the rolled-back test session instead."""
    app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(db_session)
    return client


def test_iteration_loads_one_batch_at_a_time(db_session: Session, db_engine: Engine) -> None:
    _insert_rows(db_session, 2500)
    db_session.expunge_all()
    stream_flags: list[bool] = []

    def on_execute(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "podcasts" in statement:
            stream_flags.append(bool(context.execution_options.get("stream_results")))

    event.listen(db_engine, "before_cursor_execute", on_execute)
    try:
        rows: Iterator[Podcast] = iter_podcasts(db_session, batch_size=1000)
        first = next(rows)
        loaded_after_first = len(db_session.identity_map)
        total = 1 + sum(1 for _ in rows)
    finally:
        event.remove(db_engine, "before_cursor_execute", on_execute)

    assert first.source_id == 1
    assert total == 2500
    # Only the first server-side batch was materialised, not the whole table.
    assert loaded_after_first <= 1000
    assert stream_flags == [True]


def test_export_streams_every_podcast_as_ndjson(
    export_client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _insert_rows(db_session, 3)

    response = export_client.get("/podcasts/export", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert "content-length" not in response.headers
    lines = response.text.splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert [r["source_id"] for r in records] == [1, 2, 3]
    assert set(records[0]) == set(PodcastOut.model_fields)


def test_export_of_empty_catalogue_is_an_empty_body(
    export_client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = export_client.get("/podcasts/export", headers=auth_headers)

    assert response.status_code == 200
    assert response.content == b""


def test_export_requires_api_key(export_client: TestClient) -> None:
    assert export_client.get("/podcasts/export").status_code == 401
