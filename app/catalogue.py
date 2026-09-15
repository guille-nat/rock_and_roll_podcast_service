"""Read queries over the podcast catalogue."""

from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import Podcast


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
        pattern = f"%{filters.q}%"
        stmt = stmt.where(or_(Podcast.title.ilike(pattern), Podcast.author.ilike(pattern)))
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
