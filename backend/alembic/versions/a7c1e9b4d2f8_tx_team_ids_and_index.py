"""add team_id/other_team_id to transactions + feed index; merge fcm & training heads

Revision ID: a7c1e9b4d2f8
Revises: b7e2d9f1a3c6, d7f4a1b9c2e3
Create Date: 2026-07-27

Merges the two open heads (fcm_token + training_fields) and adds stable team
identity to transactions so the feed can be filtered per-team (rename-proof) and
paginated efficiently.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a7c1e9b4d2f8'
down_revision = ('b7e2d9f1a3c6', 'd7f4a1b9c2e3')
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('team_id', UUID(as_uuid=True), nullable=True))
    op.add_column('transactions', sa.Column('other_team_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_transactions_team_id', 'transactions', 'teams', ['team_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_transactions_other_team_id', 'transactions', 'teams', ['other_team_id'], ['id'],
    )
    # Keyset-pagination index: newest-first feed within a league+season.
    op.create_index(
        'ix_transactions_feed', 'transactions',
        ['league_id', 'season_id', sa.text('created_at DESC'), sa.text('id DESC')],
    )


def downgrade():
    op.drop_index('ix_transactions_feed', table_name='transactions')
    op.drop_constraint('fk_transactions_other_team_id', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_team_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'other_team_id')
    op.drop_column('transactions', 'team_id')
