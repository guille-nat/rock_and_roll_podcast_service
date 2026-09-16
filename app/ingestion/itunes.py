"""Podcast sources: the iTunes Search API and the stored fixtures that replay it.

Both expose the same two calls so the ingestion code does not care which one it gets.
"""

import json
import logging
from pathlib import Path
from typing import Any, Protocol

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

ITUNES_BASE_URL = "https://itunes.apple.com"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "itunes"

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
            # The traceback goes to the log; the response body carries a fixed message.
            logger.exception("iTunes request failed after retries: %s %s", path, params)
            raise UpstreamError("The podcast source is unavailable") from exc

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
            logger.error("iTunes returned %s for %s %s", response.status_code, path, params)
            raise UpstreamError("The podcast source rejected the request")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            logger.exception("iTunes returned a body that is not JSON for %s %s", path, params)
            raise UpstreamError("The podcast source returned an unreadable response") from exc


def fixture_slug(term: str) -> str:
    """File-name slug for a search term: the only naming convention the fixtures rely on."""
    return term.replace(" ", "_")


class FixtureSource:
    """Replays iTunes responses stored under tests/fixtures/itunes (no network).

    Every fixture is loaded once at construction: `search_<slug>.json` files are indexed
    by slug and every record in them (plus any `lookup_<id>.json`) by collectionId, so
    lookups are dictionary hits instead of repeated file scans.
    """

    def __init__(self, directory: Path) -> None:
        self._searches: dict[str, list[RawPodcast]] = {}
        self._by_id: dict[int, RawPodcast] = {}
        for path in sorted(directory.glob("*.json")):
            results = _results(json.loads(path.read_text(encoding="utf-8")))
            if path.stem.startswith("search_"):
                self._searches[path.stem.removeprefix("search_")] = results
            for record in results:
                collection_id = record.get("collectionId")
                if isinstance(collection_id, int):
                    self._by_id.setdefault(collection_id, record)
        if not self._searches:
            raise UpstreamError(f"No search fixtures found in {directory}")

    def search(self, term: str) -> list[RawPodcast]:
        try:
            return self._searches[fixture_slug(term)]
        except KeyError:
            raise UpstreamError(f"No fixture for search term {term!r}") from None

    def lookup(self, source_id: int) -> RawPodcast | None:
        return self._by_id.get(source_id)


def _results(data: Any) -> list[RawPodcast]:
    """Pull the `results` list out of an iTunes payload, failing loudly on a bad shape."""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise UpstreamError("iTunes payload has no 'results' list")
    results: list[RawPodcast] = data["results"]
    return results


def open_source(settings: Settings) -> PodcastSource:
    """Build the source selected by INGEST_SOURCE. The caller closes an ITunesClient."""
    if settings.ingest_source == "fixtures":
        return FixtureSource(FIXTURES_DIR)
    return ITunesClient(ITUNES_BASE_URL, settings.itunes_timeout_seconds)
