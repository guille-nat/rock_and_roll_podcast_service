"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import BigInteger, DateTime, Identity, MetaData, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Deterministic constraint names, so Alembic migrations can refer to them.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    # PostgreSQL has no performance difference between TEXT and VARCHAR(n), and
    # iTunes gives no length guarantees, so every string column is TEXT.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: Text,
        datetime: DateTime(timezone=True),
    }


class Podcast(Base):
    __tablename__ = "podcasts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # iTunes collectionId. The unique constraint is the idempotency key for ingestion.
    source_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str]
    author: Mapped[str]
    # iTunes Search does not return descriptions; they would require parsing each RSS feed.
    description: Mapped[str | None]
    genre: Mapped[str | None] = mapped_column(index=True)
    country: Mapped[str | None] = mapped_column(index=True)
    feed_url: Mapped[str | None]
    artwork_url: Mapped[str | None]
    # List of hex colour strings, e.g. ["#1a2b3c", ...]. None when the artwork failed.
    color_palette: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # clock_timestamp() instead of now(): now() is frozen at transaction start, so every
    # row updated inside one large bulk transaction would share the same timestamp.
    # onupdate only covers ORM/Core UPDATEs; an ON CONFLICT DO UPDATE must set it explicitly.
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=text("clock_timestamp()"),
    )

    def __repr__(self) -> str:
        return f"Podcast(id={self.id!r}, source_id={self.source_id!r}, title={self.title!r})"
