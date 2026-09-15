import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Podcast


def test_migrations_match_models(db_engine: Engine, alembic_config: Config) -> None:
    # Raises if the model changed without a migration.
    command.check(alembic_config)


def test_source_id_is_unique(db_session: Session) -> None:
    db_session.add(Podcast(source_id=1, title="First", author="A"))
    db_session.flush()

    db_session.add(Podcast(source_id=1, title="Second", author="B"))

    with pytest.raises(IntegrityError, match="uq_podcasts_source_id"):
        db_session.flush()


def test_minimal_podcast_gets_null_optionals_and_server_timestamps(db_session: Session) -> None:
    podcast = Podcast(source_id=2, title="Minimal", author="A")
    db_session.add(podcast)
    db_session.flush()
    db_session.refresh(podcast)

    assert podcast.description is None
    assert podcast.color_palette is None
    assert podcast.created_at.tzinfo is not None
    assert podcast.updated_at == podcast.created_at


def test_updated_at_advances_on_update(db_session: Session) -> None:
    podcast = Podcast(source_id=3, title="Before", author="A")
    db_session.add(podcast)
    db_session.flush()

    podcast.title = "After"
    db_session.flush()
    db_session.refresh(podcast)

    # clock_timestamp() moves within the transaction; now() would not.
    assert podcast.updated_at > podcast.created_at
