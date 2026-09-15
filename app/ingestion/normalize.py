"""Turn raw iTunes records into clean, validated podcast data."""

from html.parser import HTMLParser
from typing import Any, Self

from pydantic import BaseModel, ValidationError, field_validator


class _TextExtractor(HTMLParser):
    """Collects the text nodes of an HTML fragment, dropping every tag."""

    def __init__(self) -> None:
        # convert_charrefs resolves entities such as &amp; and &#39; into characters.
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(text: str) -> str:
    """Remove HTML tags and resolve entities using a real parser, never a regex."""
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def clean_text(value: object) -> str | None:
    """Normalise a free-text field: strip HTML, trim and collapse whitespace.

    Anything that is not a string, or ends up empty, becomes None so the database
    never stores empty strings.
    """
    if not isinstance(value, str):
        return None
    cleaned = " ".join(strip_html(value).split())
    return cleaned or None


class PodcastIn(BaseModel):
    """A validated, normalised podcast ready to be upserted.

    Text fields are cleaned before validation, so a title made only of tags or spaces
    fails the same way as a missing one.
    """

    source_id: int
    title: str
    author: str
    genre: str | None = None
    country: str | None = None
    feed_url: str | None = None
    artwork_url: str | None = None

    @field_validator(
        "title", "author", "genre", "country", "feed_url", "artwork_url", mode="before"
    )
    @classmethod
    def _clean(cls, value: object) -> str | None:
        return clean_text(value)

    @classmethod
    def from_itunes(cls, raw: dict[str, Any]) -> Self:
        """Map the iTunes Search API field names onto the catalogue's columns."""
        # model_validate rather than the constructor: the raw values are untyped and
        # validation, not the type checker, is what decides whether they are acceptable.
        return cls.model_validate(
            {
                "source_id": raw.get("collectionId"),
                "title": raw.get("collectionName"),
                "author": raw.get("artistName"),
                "genre": raw.get("primaryGenreName"),
                "country": raw.get("country"),
                "feed_url": raw.get("feedUrl"),
                # The 600px artwork gives a better palette; older records only have 100px.
                "artwork_url": raw.get("artworkUrl600") or raw.get("artworkUrl100"),
            }
        )


def skip_reason(error: ValidationError) -> str:
    """Summarise a validation failure as a short reason code for the ingestion report."""
    first = error.errors()[0]
    field = str(first["loc"][0]) if first["loc"] else "record"
    if first["type"] in ("missing", "string_type", "int_type"):
        # A None or absent value: "missing_title", "missing_source_id", ...
        return f"missing_{field}"
    return f"invalid_{field}"
