import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LeagueStatus(str, enum.Enum):
    setup     = 'setup'
    regular   = 'regular'
    playoffs  = 'playoffs'
    offseason = 'offseason'


class SeasonStatus(str, enum.Enum):
    regular   = 'regular'
    playoffs  = 'playoffs'
    offseason = 'offseason'
    complete  = 'complete'


class GameStatus(str, enum.Enum):
    scheduled = 'scheduled'
    complete  = 'complete'


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
    created_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now)


class Team(Base):
    __tablename__ = 'teams'

    id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:   Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    name:        Mapped[str]            = mapped_column(String(100), nullable=False)
    conference:  Mapped[str]            = mapped_column(String(50), nullable=False)
    division:    Mapped[str]            = mapped_column(String(50), nullable=False)
    is_cpu:      Mapped[bool]           = mapped_column(Boolean, default=True)
    coach_id:    Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey('coaches.id'), nullable=True)


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


class Season(Base):
    __tablename__ = 'seasons'

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id:      Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), ForeignKey('leagues.id'), nullable=False)
    season_number:  Mapped[int]         = mapped_column(Integer, nullable=False)
    status:         Mapped[SeasonStatus]= mapped_column(default=SeasonStatus.regular)
    current_week:   Mapped[int]         = mapped_column(Integer, default=1)
    created_at:     Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=_now)


class Game(Base):
    __tablename__ = 'games'

    id:           Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id:    Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('seasons.id'), nullable=False)
    week:         Mapped[int]            = mapped_column(Integer, nullable=False)
    home_team_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=False)
    away_team_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey('teams.id'), nullable=False)
    home_score:   Mapped[int|None]       = mapped_column(Integer, nullable=True)
    away_score:   Mapped[int|None]       = mapped_column(Integer, nullable=True)
    status:       Mapped[GameStatus]     = mapped_column(default=GameStatus.scheduled)
    played_at:    Mapped[datetime|None]  = mapped_column(DateTime(timezone=True), nullable=True)

    home_team: Mapped['Team'] = relationship('Team', foreign_keys=[home_team_id], lazy='noload')
    away_team: Mapped['Team'] = relationship('Team', foreign_keys=[away_team_id], lazy='noload')
