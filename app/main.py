"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_exception_handlers
from app.routers import health, ingest, podcasts

# Read settings at import time so a missing API_KEY or DATABASE_URL
# fails the process at startup instead of on the first request.
get_settings()

# Application logs (ingestion progress, skipped records) at INFO; uvicorn only
# configures its own loggers.
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")

app = FastAPI(
    title="Rock & Roll Podcast Service",
    description="Catalogue of rock & roll podcasts ingested from the iTunes Search API.",
)

register_exception_handlers(app)
app.include_router(health.router)
app.include_router(podcasts.router)
app.include_router(ingest.router)
