"""add fcm_token to coaches

Revision ID: b7e2d9f1a3c6
Revises: a3f8c1d2e4b5
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e2d9f1a3c6'
down_revision = 'a3f8c1d2e4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('coaches', sa.Column('fcm_token', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('coaches', 'fcm_token')
