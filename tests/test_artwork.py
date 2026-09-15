from functools import partial
from io import BytesIO

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artwork import extract_palette, extract_palettes, fetch_palette
from app.ingest import ingest_records
from app.models import Podcast


def _png(colors: list[tuple[int, int, int]]) -> bytes:
    """A PNG made of equal vertical stripes, one per colour."""
    width = 20 * len(colors)
    image = Image.new("RGB", (width, 20))
    for index, color in enumerate(colors):
        image.paste(color, (index * 20, 0, (index + 1) * 20, 20))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_palette_returns_dominant_hex_colours() -> None:
    palette = extract_palette(_png([(255, 0, 0), (0, 0, 255)]))

    assert set(palette) == {"#ff0000", "#0000ff"}
    assert all(len(color) == 7 and color.startswith("#") for color in palette)


def test_extract_palette_caps_the_number_of_colours() -> None:
    colors = [(i * 40, 255 - i * 40, (i * 90) % 256) for i in range(6)]

    assert len(extract_palette(_png(colors))) <= 5


def test_fetch_palette_returns_none_on_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    with httpx.Client(transport=transport) as client:
        assert fetch_palette(client, "https://example.com/a.jpg") is None


def test_fetch_palette_returns_none_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_palette(client, "https://example.com/a.jpg") is None


def test_fetch_palette_returns_none_when_body_is_not_an_image() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>"))

    with httpx.Client(transport=transport) as client:
        assert fetch_palette(client, "https://example.com/a.jpg") is None


def test_extract_palettes_downloads_each_url_once_and_isolates_failures() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/bad.jpg":
            return httpx.Response(404)
        return httpx.Response(200, content=_png([(0, 255, 0)]))

    urls = ["https://x/ok.jpg", "https://x/bad.jpg", "https://x/ok.jpg"]
    palettes = extract_palettes(urls, workers=2, transport=httpx.MockTransport(handler))

    assert palettes == {"https://x/ok.jpg": ["#00ff00"], "https://x/bad.jpg": None}
    assert sorted(calls) == ["/bad.jpg", "/ok.jpg"]


def test_failed_artwork_download_stores_podcast_with_null_palette(db_session: Session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/2.jpg":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, content=_png([(10, 20, 30)]))

    extractor = partial(extract_palettes, transport=httpx.MockTransport(handler))
    raw = [
        {"collectionId": i, "collectionName": f"P{i}", "artistName": "A", "artworkUrl600": f"https://x/{i}.jpg"}
        for i in (1, 2)
    ]

    summary = ingest_records(db_session, raw, extractor)

    assert summary.stored == 2
    rows = {p.source_id: p.color_palette for p in db_session.scalars(select(Podcast))}
    assert rows == {1: ["#0a141e"], 2: None}
