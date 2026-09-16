"""Application exceptions and the single error response shape.

Every error leaves the service as ``{"error": {"code": ..., "message": ...}}``,
whether it was raised by our code, by request validation or by the framework itself.
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base class for errors that map directly to an HTTP response."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthenticatedError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class UpstreamError(ApiError):
    """The upstream data source (iTunes) failed or returned something unusable."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_error"


# Codes for errors raised by the framework itself (unknown route, wrong method, ...).
_HTTP_STATUS_CODES: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=headers,
    )


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message)


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # A single message cannot describe several invalid fields, so the Pydantic error
    # list travels alongside it. Its entries are JSON-serialisable already.
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Invalid request",
        details=list(exc.errors()),
    )


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # The traceback stays server-side; the body must not leak internals.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal server error"
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette types every handler as taking a bare `Exception`, although it only ever
    # dispatches the registered class, so the narrower signatures need an ignore.
    app.add_exception_handler(ApiError, _handle_api_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected_error)
