"""Read endpoints for the podcast catalogue."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import catalogue
from app.auth import require_api_key
from app.db import SessionFactory, get_session, get_session_factory
from app.catalogue import PodcastFilters
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
    items, total = catalogue.list_podcasts(session, filters)
    return PodcastPage(
        items=[PodcastOut.model_validate(item) for item in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def _ndjson_lines(session_factory: SessionFactory) -> Iterator[bytes]:
    """One JSON object per line. Runs after the endpoint has returned, while streaming.

    The session is opened and closed here, inside the generator, so it lives exactly as
    long as the stream does. A session from a `Depends` would be tied to the request
    lifecycle instead, which has changed between FastAPI versions.
    """
    with session_factory() as session:
        for podcast in catalogue.iter_podcasts(session):
            yield PodcastOut.model_validate(podcast).model_dump_json().encode() + b"\n"


# Declared before /{podcast_id}: otherwise "export" would be parsed as an id and rejected.
@router.get(
    "/export",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/x-ndjson": {}}, "description": "NDJSON stream"}},
)
def export_podcasts(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> StreamingResponse:
    """Stream the whole catalogue as NDJSON, one podcast per line."""
    return StreamingResponse(
        _ndjson_lines(session_factory),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="podcasts.ndjson"'},
    )


@router.get("/{podcast_id}", response_model=PodcastOut, responses={404: {"model": ErrorResponse}})
def get_podcast(
    podcast_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> PodcastOut:
    return PodcastOut.model_validate(catalogue.get_podcast(session, podcast_id))
