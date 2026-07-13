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


class FcmTokenRequest(BaseModel):
    token: str


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
    id:                        uuid.UUID
    name:                      str
    status:                    str
    current_week:              int | None
    season_status:             str | None
    created_at:                datetime
    offseason_days_remaining:  int | None = None
    preseason_days_remaining:  int | None = None


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
    scoring_plays:  list | None = None


class PlayerScoutItem(BaseModel):
    id:                     uuid.UUID
    name:                   str
    position:               str
    age:                    int
    composite_label:        str
    named_stat_labels:      dict[str, str]
    injury_games_remaining: int


class PlayerRosterItem(BaseModel):
    id:                     uuid.UUID
    name:                   str
    position:               str
    age:                    int
    composite:              float
    named_stats:            dict[str, int]
    injury_games_remaining: int
    on_ir:                  bool


class SignFARequest(BaseModel):
    player_id:      uuid.UUID
    drop_player_id: uuid.UUID | None = None


class TrainRequest(BaseModel):
    player_id: uuid.UUID
    points:    int


class TrainingPlayerItem(BaseModel):
    id:                     uuid.UUID
    name:                   str
    position:               str
    age:                    int
    composite:              float
    named_stats:            dict[str, int]
    train_sessions_used:    int
    sessions_remaining:     int
    trained_this_week:      bool
    injury_games_remaining: int


class TrainingStateResponse(BaseModel):
    train_points:        int
    current_week:        int
    in_regular_season:   bool
    sessions_per_player: int
    players:             list[TrainingPlayerItem]


class TrainResultResponse(BaseModel):
    outcome:             str            # upgrade | decline | injury | none
    message:             str
    stat_changed:        str | None = None
    delta:               int = 0
    composite:           float
    injury_games:        int = 0
    train_points:        int            # team points remaining after this session
    train_sessions_used: int            # this player's sessions used after this session
    sessions_remaining:  int


class ActivateRequest(BaseModel):
    drop_player_id:     uuid.UUID | None = None
    activate_player_id: uuid.UUID


class TeamRenameRequest(BaseModel):
    name: str


class ReleaseRequest(BaseModel):
    player_id: uuid.UUID


class ReleaseResponse(BaseModel):
    thin_positions: list[str]


class TradeRequest(BaseModel):
    my_player_id:    uuid.UUID
    their_player_id: uuid.UUID


class TradeResponse(BaseModel):
    accepted: bool
    reason:   str


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
    ties:               int
    points_for:         int
    points_against:     int
    point_differential: int


class StandingsResponse(BaseModel):
    standings: list[StandingRow]


class PlayerStatsResponse(BaseModel):
    ytd:    dict[str, int]
    career: dict[str, int]


class GroupComposite(BaseModel):
    composite: float
    label:     str


class GamePlanRequest(BaseModel):
    off_gameplan: str
    def_gameplan: str


class TeamMatchupSide(BaseModel):
    team_id:      uuid.UUID
    name:         str
    wins:         int
    losses:       int
    ties:         int
    groups:       dict[str, GroupComposite]
    off_gameplan: str = 'balanced'
    def_gameplan: str = 'balanced'


class GameMatchupResponse(BaseModel):
    game_id:    uuid.UUID
    week:       int
    is_playoff: bool
    home_team:  TeamMatchupSide
    away_team:  TeamMatchupSide


class PassingLeader(BaseModel):
    player_id:            uuid.UUID
    player_name:          str
    team_name:            str
    position:             str
    pass_yards:           int
    pass_tds:             int
    pass_completions:     int
    pass_attempts:        int
    interceptions_thrown: int


class RushingLeader(BaseModel):
    player_id:     uuid.UUID
    player_name:   str
    team_name:     str
    position:      str
    rush_yards:    int
    rush_tds:      int
    rush_attempts: int


class ReceivingLeader(BaseModel):
    player_id:       uuid.UUID
    player_name:     str
    team_name:       str
    position:        str
    receiving_yards: int
    receiving_tds:   int
    receptions:      int


class DefenseLeader(BaseModel):
    player_id:         uuid.UUID
    player_name:       str
    team_name:         str
    position:          str
    tackles:           int
    sacks:             int
    interceptions:     int
    forced_fumbles:    int
    fumble_recoveries: int


class LeagueLeadersResponse(BaseModel):
    passing:         list[PassingLeader]
    rushing:         list[RushingLeader]
    receiving:       list[ReceivingLeader]
    def_tackles:     list[DefenseLeader]
    def_sacks:       list[DefenseLeader]
    def_interceptions: list[DefenseLeader]


class TeamNewsResponse(BaseModel):
    headline: str


class TeamSeasonSummary(BaseModel):
    season_number:  int
    wins:           int
    losses:         int
    ties:           int
    playoff_result: str  # missed | first_round | conf_champ | runner_up | champion


class TeamHistoryResponse(BaseModel):
    team_id:   uuid.UUID
    team_name: str
    seasons:   list[TeamSeasonSummary]


class CoachTeamItem(BaseModel):
    team_id:    uuid.UUID
    team_name:  str
    league_id:  uuid.UUID
    league_name: str
    conference: str
    division:   str


class DraftPickRequest(BaseModel):
    player_id: uuid.UUID


class DraftPlayerItem(BaseModel):
    id:        str
    name:      str
    position:  str
    age:       int
    composite: str
    stats:     dict[str, str]


class DraftPickRecord(BaseModel):
    pick:            int
    round:           int
    team_id:         str
    team_name:       str = ''
    player_name:     str
    position:        str
    composite_label: str


class TransactionItem(BaseModel):
    tx_type:           str
    team_name:         str
    player_name:       str
    player_position:   str
    other_team_name:   str | None
    other_player_name: str | None
    created_at:        str


class DraftStateResponse(BaseModel):
    is_done:           bool
    current_pick:      int
    total_picks:       int
    current_round:     int | None
    rounds:            int
    is_human_turn:     bool
    current_team_id:   str | None
    current_team_name: str
    available:         list[DraftPlayerItem]
    recent_picks:      list[DraftPickRecord]
    draft_complete:    bool = False
