"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ErrorBody(BaseModel):
    code: str
    message: str
    # Only present on validation errors: the list of invalid fields from Pydantic.
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    """The shape of every error response, whatever raised it."""

    error: ErrorBody


class PodcastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    title: str
    author: str
    description: str | None
    genre: str | None
    country: str | None
    feed_url: str | None
    artwork_url: str | None
    color_palette: list[str] | None
    created_at: datetime
    updated_at: datetime


class PodcastPage(BaseModel):
    items: list[PodcastOut]
    # Number of podcasts matching the filters, regardless of pagination.
    total: int
    limit: int
    offset: int
