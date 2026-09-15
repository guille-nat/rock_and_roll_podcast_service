import pytest
from pydantic import ValidationError

from app.ingestion.normalize import PodcastIn, clean_text, skip_reason, strip_html

RAW = {
    "collectionId": 123,
    "collectionName": "  The <b>Rock</b>   Show ",
    "artistName": "Jane &amp; John",
    "primaryGenreName": "Music",
    "country": "USA",
    "feedUrl": "https://example.com/feed.xml",
    "artworkUrl100": "https://example.com/100.jpg",
    "artworkUrl600": "https://example.com/600.jpg",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ("Tom &amp; Jerry &#39;live&#39;", "Tom & Jerry 'live'"),
        ("<a href='x'>link</a><br/>next", "linknext"),
        ("no tags", "no tags"),
    ],
)
def test_strip_html(raw: str, expected: str) -> None:
    assert strip_html(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello    world \n", "hello world"),
        ("<i></i>   ", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_clean_text(raw: object, expected: str | None) -> None:
    assert clean_text(raw) == expected


def test_from_itunes_maps_and_cleans_fields() -> None:
    podcast = PodcastIn.from_itunes(RAW)

    assert podcast.source_id == 123
    assert podcast.title == "The Rock Show"
    assert podcast.author == "Jane & John"
    assert podcast.genre == "Music"
    assert podcast.artwork_url == "https://example.com/600.jpg"


def test_from_itunes_falls_back_to_small_artwork() -> None:
    raw = {**RAW, "artworkUrl600": None}

    assert PodcastIn.from_itunes(raw).artwork_url == "https://example.com/100.jpg"


def test_optional_fields_default_to_none() -> None:
    podcast = PodcastIn.from_itunes({"collectionId": 1, "collectionName": "T", "artistName": "A"})

    assert (podcast.genre, podcast.country, podcast.feed_url, podcast.artwork_url) == (
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({**RAW, "collectionId": None}, "missing_source_id"),
        ({k: v for k, v in RAW.items() if k != "collectionName"}, "missing_title"),
        ({**RAW, "collectionName": "<b> </b>"}, "missing_title"),
        ({**RAW, "artistName": ""}, "missing_author"),
        ({**RAW, "collectionId": "not-a-number"}, "invalid_source_id"),
    ],
)
def test_invalid_records_report_a_reason(raw: dict[str, object], reason: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        PodcastIn.from_itunes(raw)

    assert skip_reason(exc_info.value) == reason


def test_numeric_string_source_id_is_accepted() -> None:
    assert PodcastIn.from_itunes({**RAW, "collectionId": "123"}).source_id == 123
