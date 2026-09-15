"""Podcast sources: the iTunes Search API and the stored fixtures that replay it.

Both expose the same two calls so the ingestion code does not care which one it gets.
"""

import json
import logging
from pathlib import Path
from typing import Any, Protocol, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.errors import UpstreamError

logger = logging.getLogger(__name__)

RawPodcast = dict[str, Any]


class PodcastSource(Protocol):
    def search(self, term: str) -> list[RawPodcast]:
        """Return the raw iTunes records matching a search term."""

    def lookup(self, source_id: int) -> RawPodcast | None:
        """Return the raw iTunes record for a collectionId, or None if unknown."""


class _RetryableStatus(Exception):
    """A 5xx from iTunes: transient, worth another attempt."""


# Only transport failures and 5xx are retried. A 4xx means the request itself is wrong
# and repeating it cannot help, so it fails straight away.
_RETRYABLE = (httpx.TransportError, _RetryableStatus)


class ITunesClient:
    """Thin client over the iTunes Search API. Raises UpstreamError on any failure."""

    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def search(self, term: str) -> list[RawPodcast]:
        data = self._get("/search", {"media": "podcast", "term": term, "limit": 200})
        return _results(data)

    def lookup(self, source_id: int) -> RawPodcast | None:
        data = self._get("/lookup", {"id": source_id, "entity": "podcast"})
        results = _results(data)
        return results[0] if results else None

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            return self._get_with_retry(path, params)
        except _RETRYABLE as exc:
            raise UpstreamError(f"iTunes request failed after retries: {exc}") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    def _get_with_retry(self, path: str, params: dict[str, Any]) -> Any:
        response = self._client.get(path, params=params)
        if response.status_code >= 500:
            raise _RetryableStatus(f"iTunes returned {response.status_code}")
        if response.status_code >= 400:
            raise UpstreamError(f"iTunes returned {response.status_code} for {path}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise UpstreamError("iTunes returned a body that is not JSON") from exc


class FixtureSource:
    """Replays iTunes responses stored under tests/fixtures/itunes (no network)."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def search(self, term: str) -> list[RawPodcast]:
        path = self._directory / f"search_{term.replace(' ', '_')}.json"
        if not path.exists():
            raise UpstreamError(f"No fixture for search term {term!r} at {path}")
        return _results(json.loads(path.read_text(encoding="utf-8")))

    def lookup(self, source_id: int) -> RawPodcast | None:
        path = self._directory / f"lookup_{source_id}.json"
        if path.exists():
            results = _results(json.loads(path.read_text(encoding="utf-8")))
            return results[0] if results else None
        # Fall back to scanning the search fixtures, so any fixture podcast can be looked up.
        for search_file in sorted(self._directory.glob("search_*.json")):
            for record in _results(json.loads(search_file.read_text(encoding="utf-8"))):
                if record.get("collectionId") == source_id:
                    return record
        return None


def _results(data: Any) -> list[RawPodcast]:
    """Pull the `results` list out of an iTunes payload, failing loudly on a bad shape."""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise UpstreamError("iTunes payload has no 'results' list")
    results: list[RawPodcast] = data["results"]
    return results


def open_source(settings: Settings) -> PodcastSource:
    """Build the source selected by INGEST_SOURCE. The caller closes an ITunesClient."""
    if settings.ingest_source == "fixtures":
        return FixtureSource(settings.fixtures_dir)
    return ITunesClient(settings.itunes_base_url, settings.itunes_timeout_seconds)
