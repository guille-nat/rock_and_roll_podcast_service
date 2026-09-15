"""Read endpoints for the podcast catalogue."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import podcasts
from app.auth import require_api_key
from app.db import get_session
from app.podcasts import PodcastFilters
from app.schemas import ErrorResponse, PodcastOut, PodcastPage

router = APIRouter(
    prefix="/podcasts",
    tags=["podcasts"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}},
)


def podcast_filters(
    genre: Annotated[str | None, Query(description="Exact genre, case-insensitive")] = None,
    country: Annotated[str | None, Query(description="Exact country, case-insensitive")] = None,
    q: Annotated[str | None, Query(min_length=1, description="Search in title and author")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PodcastFilters:
    return PodcastFilters(genre=genre, country=country, q=q, limit=limit, offset=offset)


@router.get("", response_model=PodcastPage)
def list_podcasts(
    filters: Annotated[PodcastFilters, Depends(podcast_filters)],
    session: Annotated[Session, Depends(get_session)],
) -> PodcastPage:
    items, total = podcasts.list_podcasts(session, filters)
    return PodcastPage(
        items=[PodcastOut.model_validate(item) for item in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


# NOTE: /podcasts/export (streaming) must be declared before /{podcast_id}, otherwise
# "export" would be matched as a podcast id and rejected with 422.


@router.get("/{podcast_id}", response_model=PodcastOut, responses={404: {"model": ErrorResponse}})
def get_podcast(
    podcast_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> PodcastOut:
    return PodcastOut.model_validate(podcasts.get_podcast(session, podcast_id))
