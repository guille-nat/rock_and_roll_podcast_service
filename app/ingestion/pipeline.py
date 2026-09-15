"""Ingestion: fetch raw records, normalise them and upsert them into the catalogue.

Flow: fetch across terms -> de-duplicate by source_id in memory -> validate and
normalise each record -> upsert in batches -> fetch artwork palettes -> report.
"""

import logging
from collections import Counter
from collections.abc import Callable, Iterable
from itertools import batched

from pydantic import ValidationError
from sqlalchemy import Boolean, bindparam, func, literal_column, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.ingestion.itunes import PodcastSource, RawPodcast
from app.models import Podcast
from app.ingestion.normalize import PodcastIn, skip_reason
from app.schemas import IngestSummary

logger = logging.getLogger(__name__)

# The working definition of "rock & roll" for this catalogue. iTunes Search caps every
# query at 200 results with no paging, so a batch is the union of these searches.
SEARCH_TERMS: tuple[str, ...] = (
    "rock",
    "rock and roll",
    "classic rock",
    "punk rock",
    "hard rock",
    "metal",
    "indie rock",
)

# Rows per INSERT statement. Seven bound values per row keeps this far below
# PostgreSQL's parameter limit while avoiding one round trip per podcast.
UPSERT_BATCH_SIZE = 500

# Given artwork URLs, returns a palette (or None when the image could not be processed).
PaletteExtractor = Callable[[Iterable[str]], dict[str, list[str] | None]]


def upsert_podcasts(session: Session, records: list[PodcastIn]) -> tuple[int, int]:
    """Insert or update podcasts by source_id. Returns (inserted, updated) counts.

    Idempotency lives in the database: INSERT ... ON CONFLICT (source_id) DO UPDATE is a
    single atomic statement, so concurrent ingestions cannot create duplicates the way an
    application-level "if exists then update" would.
    """
    inserted = 0
    updated = 0
    # Lock rows in a consistent order: two concurrent ingestions upserting the same
    # podcasts in different orders could otherwise deadlock each other.
    ordered = sorted(records, key=lambda record: record.source_id)
    for batch in batched(ordered, UPSERT_BATCH_SIZE):
        stmt = insert(Podcast).values([record.model_dump() for record in batch])
        stmt = stmt.on_conflict_do_update(
            index_elements=[Podcast.source_id],
            set_={
                "title": stmt.excluded.title,
                "author": stmt.excluded.author,
                "genre": stmt.excluded.genre,
                "country": stmt.excluded.country,
                "feed_url": stmt.excluded.feed_url,
                "artwork_url": stmt.excluded.artwork_url,
                # onupdate does not fire for ON CONFLICT updates, so set it explicitly.
                "updated_at": func.clock_timestamp(),
            },
            # color_palette is deliberately not overwritten here: the previous palette
            # stays until the new download succeeds.
        )
        # PostgreSQL sets xmax to 0 on a freshly inserted row and to the deleting/updating
        # transaction id otherwise, which tells inserts and updates apart in one statement.
        result = session.execute(
            stmt.returning(literal_column("xmax = 0", Boolean).label("inserted"))
        )
        for (was_inserted,) in result:
            if was_inserted:
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def store_palettes(session: Session, palettes: dict[int, list[str] | None]) -> None:
    """Write the extracted palettes, keyed by source_id, in one executemany UPDATE."""
    if not palettes:
        return
    stmt = (
        update(Podcast)
        .where(Podcast.source_id == bindparam("sid"))
        .values(color_palette=bindparam("palette"))
    )
    # Run it on the connection, as plain Core executemany: the ORM's bulk UPDATE path
    # insists on primary keys and would try to sync objects the session does not hold.
    session.connection().execute(
        stmt, [{"sid": source_id, "palette": palette} for source_id, palette in palettes.items()]
    )


def ingest_records(
    session: Session,
    raw_records: list[RawPodcast],
    extract_palettes: PaletteExtractor | None = None,
) -> IngestSummary:
    """Validate, upsert and (optionally) colour-profile a list of raw iTunes records."""
    skipped: Counter[str] = Counter()

    # De-duplicate in memory first: the same podcast shows up under several search terms.
    unique: dict[object, RawPodcast] = {}
    for raw in raw_records:
        key = raw.get("collectionId")
        if key is not None and key in unique:
            skipped["duplicate"] += 1
        else:
            unique.setdefault(key if key is not None else object(), raw)

    records: list[PodcastIn] = []
    for raw in unique.values():
        try:
            records.append(PodcastIn.from_itunes(raw))
        except ValidationError as exc:
            reason = skip_reason(exc)
            skipped[reason] += 1
            # Skipping is never silent.
            logger.warning(
                "Skipping record collectionId=%r (%s)", raw.get("collectionId"), reason
            )

    stored, updated = upsert_podcasts(session, records)
    session.commit()

    if extract_palettes is not None:
        with_artwork = [r for r in records if r.artwork_url is not None]
        palettes_by_url = extract_palettes({r.artwork_url for r in with_artwork if r.artwork_url})
        store_palettes(
            session,
            {r.source_id: palettes_by_url.get(r.artwork_url or "") for r in with_artwork},
        )
        session.commit()

    summary = IngestSummary(
        fetched=len(raw_records),
        stored=stored,
        updated=updated,
        skipped=sum(skipped.values()),
        skipped_reasons=dict(skipped),
    )
    logger.info("Ingestion finished: %s", summary.model_dump())
    return summary


def ingest_bulk(
    session: Session,
    source: PodcastSource,
    extract_palettes: PaletteExtractor | None = None,
) -> IngestSummary:
    """Fetch every search term from the source and ingest the merged results."""
    raw_records: list[RawPodcast] = []
    for term in SEARCH_TERMS:
        results = source.search(term)
        logger.info("Fetched %d results for %r", len(results), term)
        raw_records.extend(results)
    return ingest_records(session, raw_records, extract_palettes)


def ingest_one(
    session: Session,
    source: PodcastSource,
    source_id: int,
    extract_palettes: PaletteExtractor | None = None,
) -> IngestSummary:
    """Ingest a single podcast by its iTunes collectionId."""
    raw = source.lookup(source_id)
    if raw is None:
        raise NotFoundError(f"Podcast {source_id} not found in the source")
    return ingest_records(session, [raw], extract_palettes)
