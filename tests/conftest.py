import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings

# Settings are read when the application is imported, so the environment must
# be in place before any test module imports it.
os.environ.setdefault("API_KEY", "test-api-key")

# Tests run against the same server as DATABASE_URL (exported or from .env)
# but on the podcasts_test database, which the Compose init script creates.
_test_url = make_url(Settings().database_url).set(database="podcasts_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(toml_file="pyproject.toml")


@pytest.fixture(scope="session")
def db_engine(alembic_config: Config) -> Iterator[Engine]:
    """Migrate the test database up for the session and back down afterwards."""
    from app.db import engine

    command.upgrade(alembic_config, "head")
    yield engine
    command.downgrade(alembic_config, "base")
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after each test."""
    with db_engine.connect() as connection:
        transaction = connection.begin()
        # Savepoints let a test call commit()/rollback() without ending the outer transaction.
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()
