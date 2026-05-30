"""add gameplan to teams

Revision ID: a3f8c1d2e4b5
Revises: 6a74ed0b7c9d
Create Date: 2026-05-30

"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a3f8c1d2e4b5'
down_revision: Union[str, None] = '6a74ed0b7c9d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('off_gameplan', sa.String(20), nullable=False, server_default='balanced'))
    op.add_column('teams', sa.Column('def_gameplan', sa.String(20), nullable=False, server_default='balanced'))


def downgrade() -> None:
    op.drop_column('teams', 'off_gameplan')
    op.drop_column('teams', 'def_gameplan')
