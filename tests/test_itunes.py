import json
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from app.errors import UpstreamError
from app.itunes import FixtureSource, ITunesClient

FIXTURES = Path(__file__).parent / "fixtures" / "itunes"


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry logic but skip the backoff sleeps."""
    # tenacity attaches the Retrying controller to the wrapped function but does not type it.
    retrying = ITunesClient._get_with_retry.retry  # type: ignore[attr-defined]
    monkeypatch.setattr(retrying, "wait", wait_none())


def _client(handler: httpx.MockTransport) -> ITunesClient:
    return ITunesClient("https://itunes.test", timeout=1, transport=handler)


def test_search_returns_results_and_sends_expected_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"resultCount": 1, "results": [{"collectionId": 1}]})

    with _client(httpx.MockTransport(handler)) as client:
        assert client.search("punk rock") == [{"collectionId": 1}]

    params = seen[0].url.params
    assert (params["media"], params["term"], params["limit"]) == ("podcast", "punk rock", "200")


def test_server_errors_are_retried_then_succeed() -> None:
    statuses = iter([503, 500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        body = {"resultCount": 0, "results": []} if status == 200 else {}
        return httpx.Response(status, json=body)

    with _client(httpx.MockTransport(handler)) as client:
        assert client.search("rock") == []


def test_client_errors_are_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={})

    with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamError, match="400"):
            client.search("rock")
    assert calls == 1


def test_persistent_timeouts_become_upstream_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamError, match="after retries"):
            client.search("rock")
    assert calls == 3


def test_non_json_body_is_upstream_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>"))

    with _client(transport) as client:
        with pytest.raises(UpstreamError, match="not JSON"):
            client.search("rock")


def test_lookup_returns_none_when_unknown() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"resultCount": 0, "results": []})
    )

    with _client(transport) as client:
        assert client.lookup(42) is None


def test_fixture_source_reads_search_and_lookup() -> None:
    source = FixtureSource(FIXTURES)

    results = source.search("rock and roll")
    lookup_file = next(FIXTURES.glob("lookup_*.json"))
    known_id = json.loads(lookup_file.read_text())["results"][0]["collectionId"]
    from_search = results[0]["collectionId"]

    assert len(results) > 0
    assert source.lookup(known_id) is not None
    assert source.lookup(from_search) == results[0]
    assert source.lookup(1) is None


def test_fixture_source_missing_term_is_upstream_error() -> None:
    with pytest.raises(UpstreamError, match="No fixture"):
        FixtureSource(FIXTURES).search("polka")
