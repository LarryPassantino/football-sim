"""add retired to players

Revision ID: c4d5e6f7a8b9
Revises: f3a1b2c4d5e6
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = 'f3a1b2c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('players', sa.Column('retired', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('players', 'retired')
