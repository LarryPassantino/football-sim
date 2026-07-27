"""add league_messages table (flat league message board)

Revision ID: b8d3f1a6c9e2
Revises: a7c1e9b4d2f8
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'b8d3f1a6c9e2'
down_revision = 'a7c1e9b4d2f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'league_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('leagues.id'), nullable=False),
        sa.Column('team_id', UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('coach_id', UUID(as_uuid=True), sa.ForeignKey('coaches.id'), nullable=True),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('coach_name', sa.String(length=100), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Keyset-pagination index: newest-first feed within a league.
    op.create_index(
        'ix_league_messages_feed', 'league_messages',
        ['league_id', sa.text('created_at DESC'), sa.text('id DESC')],
    )


def downgrade():
    op.drop_index('ix_league_messages_feed', table_name='league_messages')
    op.drop_table('league_messages')
