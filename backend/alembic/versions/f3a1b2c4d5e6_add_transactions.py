"""add transactions table

Revision ID: f3a1b2c4d5e6
Revises: e1f3a2b4c5d6
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f3a1b2c4d5e6'
down_revision = 'e1f3a2b4c5d6'
branch_labels = None
depends_on = None

tx_type_enum     = postgresql.ENUM('sign', 'release', 'trade', name='transactiontype', create_type=True)
tx_type_col_enum = postgresql.ENUM('sign', 'release', 'trade', name='transactiontype', create_type=False)


def upgrade():
    tx_type_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'transactions',
        sa.Column('id',                sa.UUID(),           primary_key=True),
        sa.Column('league_id',         sa.UUID(),           sa.ForeignKey('leagues.id'), nullable=False),
        sa.Column('season_id',         sa.UUID(),           sa.ForeignKey('seasons.id'), nullable=True),
        sa.Column('tx_type',           tx_type_col_enum,                                nullable=False),
        sa.Column('team_name',         sa.String(100),                              nullable=False),
        sa.Column('player_name',       sa.String(100),                              nullable=False),
        sa.Column('player_position',   sa.String(10),                               nullable=False),
        sa.Column('other_team_name',   sa.String(100),                              nullable=True),
        sa.Column('other_player_name', sa.String(100),                              nullable=True),
        sa.Column('created_at',        sa.DateTime(timezone=True),                  nullable=False),
    )
    op.create_index('ix_transactions_league_season', 'transactions', ['league_id', 'season_id'])


def downgrade():
    op.drop_index('ix_transactions_league_season', table_name='transactions')
    op.drop_table('transactions')
    tx_type_enum.drop(op.get_bind(), checkfirst=True)
