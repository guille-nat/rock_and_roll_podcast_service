"""create podcasts table

Revision ID: db6f4701854d
Revises: 
Create Date: 2026-09-14 21:44:05.611599

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'db6f4701854d'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('podcasts',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('source_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('author', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('genre', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('feed_url', sa.Text(), nullable=True),
    sa.Column('artwork_url', sa.Text(), nullable=True),
    sa.Column('color_palette', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_podcasts')),
    sa.UniqueConstraint('source_id', name=op.f('uq_podcasts_source_id'))
    )
    op.create_index(op.f('ix_podcasts_country'), 'podcasts', ['country'], unique=False)
    op.create_index(op.f('ix_podcasts_genre'), 'podcasts', ['genre'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_podcasts_genre'), table_name='podcasts')
    op.drop_index(op.f('ix_podcasts_country'), table_name='podcasts')
    op.drop_table('podcasts')
