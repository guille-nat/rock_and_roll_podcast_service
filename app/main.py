"""FastAPI application entry point."""

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_exception_handlers
from app.routers import health

# Read settings at import time so a missing API_KEY or DATABASE_URL
# fails the process at startup instead of on the first request.
get_settings()

app = FastAPI(
    title="Rock & Roll Podcast Service",
    description="Catalogue of rock & roll podcasts ingested from the iTunes Search API.",
)

register_exception_handlers(app)
app.include_router(health.router)
