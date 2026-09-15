"""Pydantic request and response schemas."""

from typing import Any, Literal

from pydantic import BaseModel


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
