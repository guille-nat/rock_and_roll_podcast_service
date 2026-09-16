"""Cover art download and colour palette extraction.

Downloads are I/O-bound, so they run concurrently in a thread pool. Every download is
guarded individually: a failed or unreadable image yields None and never aborts the
ingestion that requested it.
"""

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

PALETTE_SIZE = 5
# The palette does not need the full-resolution image; shrinking first makes
# quantisation fast and consistent regardless of the original size.
THUMBNAIL_SIZE = (200, 200)


def extract_palette(image_bytes: bytes, colors: int = PALETTE_SIZE) -> list[str]:
    """Return the dominant colours of an image as hex strings, most frequent first."""
    with Image.open(BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
    rgb.thumbnail(THUMBNAIL_SIZE)
    # Pillow's median-cut quantiser reduces the image to `colors` representative
    # colours; the result is a palette image whose pixel values index that palette.
    quantized = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []
    ordered = sorted(counts, key=lambda pair: pair[0], reverse=True)
    # In a palette ("P") image every pixel value is an int index into the palette;
    # getcolors() is typed loosely because other modes return tuples.
    indexes = [index for _, index in ordered if isinstance(index, int)]
    return ["#{:02x}{:02x}{:02x}".format(*palette[i * 3 : i * 3 + 3]) for i in indexes]


def fetch_palette(client: httpx.Client, url: str) -> list[str] | None:
    """Download one image and extract its palette; None on any failure."""
    try:
        response = client.get(url)
        response.raise_for_status()
        return extract_palette(response.content)
    except httpx.HTTPError as exc:
        logger.warning("Artwork download failed for %s: %s", url, exc)
    except Exception:
        # Deliberately broad: a cover that Pillow cannot handle for any reason must not
        # abort an ingestion whose podcasts are already committed. See NOTES.md.
        logger.exception("Artwork could not be processed for %s", url)
    return None


def extract_palettes(
    urls: Iterable[str],
    *,
    workers: int = 8,
    timeout: float = 5.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, list[str] | None]:
    """Fetch palettes for a set of URLs concurrently. Each URL is downloaded once."""
    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        return {}
    # One client shared across threads: httpx.Client is thread-safe and pools connections.
    with (
        httpx.Client(timeout=timeout, follow_redirects=True, transport=transport) as client,
        ThreadPoolExecutor(max_workers=workers) as executor,
    ):
        palettes = executor.map(lambda url: fetch_palette(client, url), unique_urls)
        return dict(zip(unique_urls, palettes, strict=True))
