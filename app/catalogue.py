"""Read queries over the podcast catalogue."""

from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import Podcast


# Rows fetched per round trip while streaming the whole catalogue.
EXPORT_BATCH_SIZE = 1000


@dataclass(frozen=True)
class PodcastFilters:
    """Filters and pagination for the catalogue listing. Built from query params."""

    genre: str | None = None
    country: str | None = None
    # Free-text search over title and author.
    q: str | None = None
    limit: int = 20
    offset: int = 0


def _filtered_query(filters: PodcastFilters) -> Select[tuple[Podcast]]:
    stmt = select(Podcast)
    if filters.genre is not None:
        stmt = stmt.where(func.lower(Podcast.genre) == filters.genre.lower())
    if filters.country is not None:
        stmt = stmt.where(func.lower(Podcast.country) == filters.country.lower())
    if filters.q is not None:
        # Backslash first, then the LIKE wildcards, or the added backslashes would be
        # escaped again. escape="\\" tells PostgreSQL which character we used.
        escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                Podcast.title.ilike(pattern, escape="\\"),
                Podcast.author.ilike(pattern, escape="\\"),
            )
        )
    return stmt


def list_podcasts(session: Session, filters: PodcastFilters) -> tuple[list[Podcast], int]:
    """Return one page of podcasts and the total number of matches."""
    stmt = _filtered_query(filters)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    # Title alone is not unique, so id is the tie-breaker that keeps pages stable.
    page = session.scalars(
        stmt.order_by(Podcast.title, Podcast.id).limit(filters.limit).offset(filters.offset)
    ).all()
    return list(page), total


def get_podcast(session: Session, podcast_id: int) -> Podcast:
    podcast = session.get(Podcast, podcast_id)
    if podcast is None:
        raise NotFoundError(f"Podcast {podcast_id} not found")
    return podcast


def iter_podcasts(session: Session, batch_size: int = EXPORT_BATCH_SIZE) -> Iterator[Podcast]:
    """Yield every podcast in id order without loading the whole table.

    yield_per keeps a server-side cursor open and fetches `batch_size` rows at a time,
    so memory use is bounded by one batch regardless of the catalogue size.
    """
    stmt = select(Podcast).order_by(Podcast.id).execution_options(yield_per=batch_size)
    yield from session.scalars(stmt)
