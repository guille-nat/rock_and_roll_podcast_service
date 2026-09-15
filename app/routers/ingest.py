"""Ingestion endpoints: bulk from the configured source, or one podcast by iTunes id."""

from collections.abc import Iterator
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.config import Settings, get_settings
from app.db import get_session
from app.ingestion import pipeline
from app.ingestion.artwork import extract_palettes
from app.ingestion.itunes import ITunesClient, PodcastSource, open_source
from app.ingestion.pipeline import PaletteExtractor
from app.schemas import ErrorResponse, IngestSummary

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)


def get_source(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[PodcastSource]:
    """The podcast source selected by INGEST_SOURCE, closed after the request."""
    source = open_source(settings)
    try:
        yield source
    finally:
        if isinstance(source, ITunesClient):
            source.close()


def get_palette_extractor(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaletteExtractor:
    return partial(
        extract_palettes,
        workers=settings.artwork_workers,
        timeout=settings.artwork_timeout_seconds,
    )


@router.post("/bulk", response_model=IngestSummary)
def ingest_bulk(
    session: Annotated[Session, Depends(get_session)],
    source: Annotated[PodcastSource, Depends(get_source)],
    extractor: Annotated[PaletteExtractor, Depends(get_palette_extractor)],
) -> IngestSummary:
    """Fetch every rock & roll search term, store the results and extract palettes."""
    return pipeline.ingest_bulk(session, source, extractor)


@router.post(
    "/{source_id}",
    response_model=IngestSummary,
    responses={404: {"model": ErrorResponse}},
)
def ingest_one(
    source_id: int,
    session: Annotated[Session, Depends(get_session)],
    source: Annotated[PodcastSource, Depends(get_source)],
    extractor: Annotated[PaletteExtractor, Depends(get_palette_extractor)],
) -> IngestSummary:
    """Ingest a single podcast by its iTunes collectionId."""
    return pipeline.ingest_one(session, source, source_id, extractor)
