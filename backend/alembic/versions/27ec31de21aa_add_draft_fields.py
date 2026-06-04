"""add_draft_fields

Revision ID: 27ec31de21aa
Revises: b7e2d9f1a3c6
Create Date: 2026-06-03 17:39:00.934275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '27ec31de21aa'
down_revision: Union[str, None] = 'b7e2d9f1a3c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE leaguestatus ADD VALUE IF NOT EXISTS 'drafting'")
    op.add_column('players', sa.Column('is_draft_eligible', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('seasons', sa.Column('draft_state', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('seasons', 'draft_state')
    op.drop_column('players', 'is_draft_eligible')
    # Note: PostgreSQL does not support removing enum values
