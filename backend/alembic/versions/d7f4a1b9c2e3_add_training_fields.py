"""add training fields to teams and players

Revision ID: d7f4a1b9c2e3
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'd7f4a1b9c2e3'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Per-team training-point budget, replenished each cycle (use-it-or-lose-it).
    op.add_column('teams', sa.Column('train_points', sa.Integer(), server_default='3', nullable=False))
    # Per-player season session cap tracking, reset at season rollover.
    op.add_column('players', sa.Column('train_sessions_used', sa.Integer(), server_default='0', nullable=False))
    # Season week a player was last trained; guards one session per player per cycle.
    op.add_column('players', sa.Column('trained_in_week', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    op.drop_column('players', 'trained_in_week')
    op.drop_column('players', 'train_sessions_used')
    op.drop_column('teams', 'train_points')
