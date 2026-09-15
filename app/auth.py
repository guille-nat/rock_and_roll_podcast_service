"""API key authentication.

A single static key, read from the API_KEY environment variable, is expected in the
X-API-Key header. Every router except /health declares `require_api_key` as a dependency.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

# auto_error=False: a missing header is handled below so the response uses the
# service's own error shape. The scheme still shows up in OpenAPI (Authorize button).
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    provided: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Reject the request with 401 unless the header carries the configured key."""
    expected = settings.api_key.get_secret_value()
    # compare_digest runs in constant time, so a wrong key cannot be guessed byte by
    # byte from response latency. It is compared as bytes because the str form only
    # accepts ASCII.
    if provided is None or not secrets.compare_digest(
        provided.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
