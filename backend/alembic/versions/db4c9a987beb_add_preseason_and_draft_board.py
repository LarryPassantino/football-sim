"""add_preseason_and_draft_board

Revision ID: db4c9a987beb
Revises: 27ec31de21aa
Create Date: 2026-06-03 23:24:58.129855

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'db4c9a987beb'
down_revision: Union[str, None] = '27ec31de21aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE leaguestatus ADD VALUE IF NOT EXISTS 'preseason'")
    op.add_column('teams', sa.Column('draft_board', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('teams', 'draft_board')
    # Note: PostgreSQL does not support removing enum values
