"""add scoring_plays to games

Revision ID: e1f3a2b4c5d6
Revises: db4c9a987beb
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e1f3a2b4c5d6'
down_revision = 'db4c9a987beb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('games', sa.Column('scoring_plays', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('games', 'scoring_plays')
