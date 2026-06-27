import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LeagueStatus(str, enum.Enum):
    setup      = 'setup'
    regular    = 'regular'
    playoffs   = 'playoffs'
    offseason  = 'offseason'
    drafting   = 'drafting'   # reserved for future live draft
    preseason  = 'preseason'


class SeasonStatus(str, enum.Enum):
    regular   = 'regular'
    playoffs  = 'playoffs'
    offseason = 'offseason'
    complete  = 'complete'


class GameStatus(str, enum.Enum):
    scheduled = 'scheduled'
    complete  = 'complete'


class TransactionType(str, enum.Enum):
    sign    = 'sign'
    release = 'release'
    trade   = 'trade'


def _now():
    return datetime.now(timezone.utc)


class League(Base):
    __tablename__ = 'leagues'

    id:         Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:       Mapped[str]          = mapped_column(String(100), unique=True, nullable=False)
    status:     Mapped[LeagueStatus] = mapped_column(default=LeagueStatus.setup)
    created_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=_now)


class Coach(Base):
    __tablename__ = 'coaches'

    id:                 Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:              Mapped[str]           = mapped_column(String(255), unique=True, nullable=False)
    hashed_password:    Mapped[str]           = mapped_column(String(255), nullable=False)
    display_name:       Mapped[str]           = mapped_column(String(100), nullable=False)
    refresh_token_hash: Mapped[str | None]    = mapped_column(String(255), nullable=True)
    fcm_token:          Mapped[str | None]    = mapped_column(String(255), nullable=True)
    created_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now)


class Team(Base):
    __tablename__ = 'teams'

    id:           Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:    Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    name:         Mapped[str]            = mapped_column(String(100), nullable=False)
    conference:   Mapped[str]            = mapped_column(String(50), nullable=False)
    division:     Mapped[str]            = mapped_column(String(50), nullable=False)
    is_cpu:       Mapped[bool]           = mapped_column(Boolean, default=True)
    coach_id:     Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey('coaches.id'), nullable=True)
    off_gameplan: Mapped[str]            = mapped_column(String(20), default='balanced', server_default='balanced')
    def_gameplan: Mapped[str]            = mapped_column(String(20), default='balanced', server_default='balanced')
    draft_board:  Mapped[dict | None]    = mapped_column(JSONB, nullable=True)


class Player(Base):
    __tablename__ = 'players'

    id:                      Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:               Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    team_id:                 Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=True)
    name:                    Mapped[str]            = mapped_column(String(100), nullable=False)
    position:                Mapped[str]            = mapped_column(String(10), nullable=False)
    age:                     Mapped[int]            = mapped_column(Integer, nullable=False)
    stats:                   Mapped[list]           = mapped_column(JSONB, nullable=False)
    composite:               Mapped[float]          = mapped_column(Float, nullable=False)
    potential:               Mapped[float]          = mapped_column(Float, nullable=False)
    injury_games_remaining:  Mapped[int]            = mapped_column(Integer, default=0)
    on_ir:                   Mapped[bool]           = mapped_column(Boolean, default=False, server_default='false')
    is_draft_eligible:       Mapped[bool]           = mapped_column(Boolean, default=False, server_default='false')
    retired:                 Mapped[bool]           = mapped_column(Boolean, default=False, server_default='false')
    career_stats:            Mapped[dict]           = mapped_column(JSONB, default=dict, server_default='{}')


class Season(Base):
    __tablename__ = 'seasons'

    id:             Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:      Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    season_number:  Mapped[int]             = mapped_column(Integer, nullable=False)
    status:         Mapped[SeasonStatus]    = mapped_column(default=SeasonStatus.regular)
    current_week:   Mapped[int]             = mapped_column(Integer, default=1)
    created_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=_now)
    completed_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    draft_state:    Mapped[dict | None]     = mapped_column(JSONB, nullable=True)


class Game(Base):
    __tablename__ = 'games'

    id:           Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id:    Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('seasons.id'), nullable=False)
    week:         Mapped[int]            = mapped_column(Integer, nullable=False)
    home_team_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=False)
    away_team_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=False)
    home_score:   Mapped[int|None]       = mapped_column(Integer, nullable=True)
    away_score:   Mapped[int|None]       = mapped_column(Integer, nullable=True)
    status:         Mapped[GameStatus]     = mapped_column(default=GameStatus.scheduled)
    is_playoff:     Mapped[bool]           = mapped_column(Boolean, default=False)
    played_at:      Mapped[datetime|None]  = mapped_column(DateTime(timezone=True), nullable=True)
    scoring_plays:  Mapped[list | None]    = mapped_column(JSONB, nullable=True)

    home_team: Mapped['Team'] = relationship('Team', foreign_keys=[home_team_id], lazy='noload')
    away_team: Mapped['Team'] = relationship('Team', foreign_keys=[away_team_id], lazy='noload')


class Transaction(Base):
    __tablename__ = 'transactions'

    id:                  Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:           Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    season_id:           Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey('seasons.id'), nullable=True)
    tx_type:             Mapped[TransactionType]= mapped_column(nullable=False)
    team_name:           Mapped[str]            = mapped_column(String(100), nullable=False)
    player_name:         Mapped[str]            = mapped_column(String(100), nullable=False)
    player_position:     Mapped[str]            = mapped_column(String(10), nullable=False)
    other_team_name:     Mapped[str|None]       = mapped_column(String(100), nullable=True)
    other_player_name:   Mapped[str|None]       = mapped_column(String(100), nullable=True)
    created_at:          Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now)


class PlayerGameStats(Base):
    __tablename__ = 'player_game_stats'

    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('games.id'), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('players.id'), nullable=False)
    team_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=False)

    # Passing
    pass_attempts:        Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    pass_completions:     Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    pass_yards:           Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    pass_tds:             Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    interceptions_thrown: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # Rushing
    rush_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    rush_yards:    Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    rush_tds:      Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # Receiving
    receptions:      Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    receiving_yards: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    receiving_tds:   Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # Ball-carrier miscellaneous
    fumbles:      Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    fumbles_lost: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # OL
    sacks_allowed: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # Defense
    tackles:           Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    sacks:             Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    interceptions:     Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    forced_fumbles:    Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    fumble_recoveries: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    player: Mapped['Player'] = relationship('Player', lazy='noload')
