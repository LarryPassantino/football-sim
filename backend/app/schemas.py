import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    refresh_token: str


class LeagueCreateRequest(BaseModel):
    name: str


class LeagueResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime

    model_config = {'from_attributes': True}


class LeagueDetailResponse(BaseModel):
    id:            uuid.UUID
    name:          str
    status:        str
    current_week:  int | None
    season_status: str | None
    created_at:    datetime


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    conference: str
    division: str
    is_cpu: bool

    model_config = {'from_attributes': True}


class GameResponse(BaseModel):
    id: uuid.UUID
    week: int
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    home_score: int | None
    away_score: int | None
    status: str

    model_config = {'from_attributes': True}


class PlayerStatLine(BaseModel):
    player_id:   uuid.UUID
    player_name: str
    position:    str

    # Passing
    pass_attempts:        int = 0
    pass_completions:     int = 0
    pass_yards:           int = 0
    pass_tds:             int = 0
    interceptions_thrown: int = 0

    # Rushing
    rush_attempts: int = 0
    rush_yards:    int = 0
    rush_tds:      int = 0

    # Receiving
    receptions:      int = 0
    receiving_yards: int = 0
    receiving_tds:   int = 0

    # Ball-carrier misc
    fumbles:      int = 0
    fumbles_lost: int = 0

    # OL
    sacks_allowed: int = 0

    # Defense
    tackles:           int = 0
    sacks:             int = 0
    interceptions:     int = 0
    forced_fumbles:    int = 0
    fumble_recoveries: int = 0


class GameDetailResponse(BaseModel):
    id:             uuid.UUID
    week:           int
    is_playoff:     bool
    home_team_id:   uuid.UUID
    home_team_name: str
    home_score:     int | None
    away_team_id:   uuid.UUID
    away_team_name: str
    away_score:     int | None
    status:         str
    played_at:      datetime | None
    home_stats:     list[PlayerStatLine]
    away_stats:     list[PlayerStatLine]


class LeagueAvailableItem(BaseModel):
    id:                uuid.UUID
    name:              str
    human_coach_count: int
    open_team_count:   int


class AvailableLeaguesResponse(BaseModel):
    leagues: list[LeagueAvailableItem]


class TeamPickerItem(BaseModel):
    id:         uuid.UUID
    name:       str
    conference: str
    division:   str

    model_config = {'from_attributes': True}


class StandingRow(BaseModel):
    team_id:            uuid.UUID
    name:               str
    conference:         str
    division:           str
    wins:               int
    losses:             int
    points_for:         int
    points_against:     int
    point_differential: int


class StandingsResponse(BaseModel):
    standings: list[StandingRow]
