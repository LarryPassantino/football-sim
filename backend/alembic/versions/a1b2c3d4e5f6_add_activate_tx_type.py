"""add activate to transactiontype enum

Revision ID: a1b2c3d4e5f6
Revises: c4d5e6f7a8b9
Create Date: 2026-06-28
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'activate'")


def downgrade():
    pass  # PostgreSQL cannot remove enum values
