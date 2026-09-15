"""Database engine and session factory."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is closed after the request."""
    with SessionLocal() as session:
        yield session


# A callable that opens a session to be used as a context manager. Streaming endpoints
# take this instead of a session, because their generator must open and close the
# session itself: the response body is produced after the endpoint has returned.
SessionFactory = Callable[[], AbstractContextManager[Session]]


def get_session_factory() -> SessionFactory:
    return SessionLocal
