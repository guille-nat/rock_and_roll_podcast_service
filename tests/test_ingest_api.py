from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import UpstreamError
from app.ingestion.itunes import FixtureSource, PodcastSource, RawPodcast
from app.main import app
from app.models import Podcast
from app.routers.ingest import get_palette_extractor, get_source

FIXTURES = Path(__file__).parent / "fixtures" / "itunes"


class BrokenSource:
    """A source whose upstream is down."""

    def search(self, term: str) -> list[RawPodcast]:
        raise UpstreamError("iTunes request failed after retries")

    def lookup(self, source_id: int) -> RawPodcast | None:
        raise UpstreamError("iTunes request failed after retries")


def _no_palettes(urls: Iterable[str]) -> dict[str, list[str] | None]:
    return dict.fromkeys(urls)


@pytest.fixture
def fixture_source(client: TestClient) -> Iterator[FixtureSource]:
    """Serve the stored iTunes fixtures and skip artwork downloads."""
    source = FixtureSource(FIXTURES)
    app.dependency_overrides[get_source] = lambda: source
    app.dependency_overrides[get_palette_extractor] = lambda: _no_palettes
    yield source
    # The client fixture clears all overrides on teardown.


def _use_source(source: PodcastSource) -> None:
    app.dependency_overrides[get_source] = lambda: source
    app.dependency_overrides[get_palette_extractor] = lambda: _no_palettes


def test_bulk_requires_api_key(client: TestClient) -> None:
    assert client.post("/ingest/bulk").status_code == 401


def test_bulk_ingests_fixtures_and_is_idempotent(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    fixture_source: FixtureSource,
) -> None:
    first = client.post("/ingest/bulk", headers=auth_headers)
    second = client.post("/ingest/bulk", headers=auth_headers)

    assert first.status_code == 200
    body = first.json()
    assert body["fetched"] == 261
    assert body["stored"] == 248
    assert body["skipped_reasons"] == {"duplicate": 13}
    assert set(body) == {"fetched", "stored", "updated", "skipped", "skipped_reasons"}

    assert second.json()["stored"] == 0
    assert second.json()["updated"] == 248
    assert db_session.scalar(select(func.count()).select_from(Podcast)) == 248


def test_single_ingest_stores_one_podcast(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    fixture_source: FixtureSource,
) -> None:
    source_id = fixture_source.search("metal")[0]["collectionId"]

    response = client.post(f"/ingest/{source_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["stored"] == 1
    assert db_session.scalars(select(Podcast.source_id)).all() == [source_id]


def test_single_ingest_unknown_id_returns_404(
    client: TestClient, auth_headers: dict[str, str], fixture_source: FixtureSource
) -> None:
    response = client.post("/ingest/1", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("source_id", ["abc", "-1", "0", str(2**63)])
def test_single_ingest_rejects_invalid_id_before_calling_the_source(
    client: TestClient, auth_headers: dict[str, str], source_id: str
) -> None:
    _use_source(BrokenSource())

    response = client.post(f"/ingest/{source_id}", headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upstream_failure_returns_502(client: TestClient, auth_headers: dict[str, str]) -> None:
    _use_source(BrokenSource())

    response = client.post("/ingest/bulk", headers=auth_headers)

    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "upstream_error", "message": "iTunes request failed after retries"}
    }
