from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.ingest import ingest_bulk, ingest_one, ingest_records
from app.itunes import FixtureSource
from app.models import Podcast

FIXTURES = Path(__file__).parent / "fixtures" / "itunes"


def _raw(source_id: int, title: str = "Title", **extra: object) -> dict[str, Any]:
    return {
        "collectionId": source_id,
        "collectionName": title,
        "artistName": "Author",
        "primaryGenreName": "Music",
        "country": "USA",
        "feedUrl": f"https://example.com/{source_id}.xml",
        "artworkUrl600": f"https://example.com/{source_id}.jpg",
        **extra,
    }


def _count(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Podcast)) or 0


def test_ingesting_the_same_batch_twice_does_not_duplicate(db_session: Session) -> None:
    batch = [_raw(1), _raw(2), _raw(3)]

    first = ingest_records(db_session, batch)
    second = ingest_records(db_session, batch)

    assert (first.stored, first.updated, first.skipped) == (3, 0, 0)
    assert (second.stored, second.updated, second.skipped) == (0, 3, 0)
    assert _count(db_session) == 3


def test_reingest_updates_fields_and_timestamp(db_session: Session) -> None:
    ingest_records(db_session, [_raw(1, title="Old")])
    before = db_session.scalars(select(Podcast)).one()
    created_at, updated_at = before.created_at, before.updated_at
    db_session.expire_all()

    ingest_records(db_session, [_raw(1, title="New")])

    after = db_session.scalars(select(Podcast)).one()
    assert after.title == "New"
    assert after.created_at == created_at
    assert after.updated_at > updated_at


def test_malformed_record_is_skipped_and_the_rest_stored(db_session: Session) -> None:
    batch: list[dict[str, Any]] = [
        _raw(1),
        _raw(2, collectionName=None),
        _raw(3),
        {"artistName": "no id"},
    ]

    summary = ingest_records(db_session, batch)

    assert summary.fetched == 4
    assert summary.stored == 2
    assert summary.skipped == 2
    assert summary.skipped_reasons == {"missing_title": 1, "missing_source_id": 1}
    assert sorted(db_session.scalars(select(Podcast.source_id))) == [1, 3]


def test_duplicates_within_a_batch_are_counted_once(db_session: Session) -> None:
    summary = ingest_records(db_session, [_raw(1), _raw(1), _raw(2), _raw(1)])

    assert (summary.stored, summary.skipped) == (2, 2)
    assert summary.skipped_reasons == {"duplicate": 2}
    assert summary.fetched == summary.stored + summary.updated + summary.skipped


def test_bulk_ingests_fixtures_across_all_terms(db_session: Session) -> None:
    summary = ingest_bulk(db_session, FixtureSource(FIXTURES))

    assert summary.fetched == 261
    assert summary.stored == 248
    assert summary.skipped_reasons.get("duplicate") == 13
    assert summary.fetched == summary.stored + summary.updated + summary.skipped
    assert _count(db_session) == 248


def test_palettes_are_stored_per_podcast(db_session: Session) -> None:
    def fake_extractor(urls: Iterable[str]) -> dict[str, list[str] | None]:
        return {url: (["#000000"] if url.endswith("1.jpg") else None) for url in urls}

    ingest_records(db_session, [_raw(1), _raw(2), _raw(3, artworkUrl600=None)], fake_extractor)

    rows = {p.source_id: p.color_palette for p in db_session.scalars(select(Podcast))}
    assert rows == {1: ["#000000"], 2: None, 3: None}


def test_ingest_one_stores_a_single_podcast(db_session: Session) -> None:
    source = FixtureSource(FIXTURES)
    source_id = source.search("rock")[0]["collectionId"]

    summary = ingest_one(db_session, source, source_id)

    assert (summary.fetched, summary.stored) == (1, 1)
    assert db_session.scalars(select(Podcast)).one().source_id == source_id


def test_ingest_one_unknown_id_raises_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError, match="not found"):
        ingest_one(db_session, FixtureSource(FIXTURES), 1)
