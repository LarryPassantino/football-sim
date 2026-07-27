import base64
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from sim.player_gen import POSITION_STATS, assign_label, assign_ceiling_label
from sim.training_sim import resolve_training_session
from sqlalchemy import func
from ..models import Coach, Game, GameStatus, League, LeagueMessage, LeagueStatus, Player, PlayerGameStats, Season, SeasonStatus, Team, Transaction, TransactionType
from ..schemas import (
    ActivateRequest, AvailableLeaguesResponse, DefenseLeader,
    GameDetailResponse, GameMatchupResponse, GamePlanRequest, GameResponse, GroupComposite,
    LeagueAvailableItem, LeagueCreateRequest, LeagueDetailResponse, LeagueLeadersResponse,
    LeagueResponse, PassingLeader, PlayerRosterItem, PlayerScoutItem, PlayerStatLine,
    PlayerStatsResponse, ReceivingLeader, ReleaseRequest, ReleaseResponse, RushingLeader,
    SignFARequest, StandingRow, StandingsResponse, TeamHistoryResponse, TeamMatchupSide,
    TeamNewsResponse, TeamPickerItem, TeamRenameRequest, TeamResponse, TradeRequest, TradeResponse,
    TrainingPlayerItem, TrainingStateResponse, TrainRequest, TrainResultResponse,
    TransactionItem, TransactionsPageResponse,
    PostMessageRequest, MessageItem, MessagesPageResponse,
)
from ..services.league_service import (
    create_league, OFFSEASON_DAYS, PRESEASON_DAYS,
    PLAYOFF_DIVISIONAL, PLAYOFF_CONF_CHAMP, PLAYOFF_LEAGUE_CHAMP,
    TRAIN_SESSIONS_PER_PLAYER, MAX_TRAIN_POINTS_PER_SESSION,
    get_draft_class, get_draft_results,
)

router = APIRouter(prefix='/leagues', tags=['leagues'])


async def _current_season_id(db: AsyncSession, league_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(Season.id)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _write_tx(
    db: AsyncSession,
    league_id: uuid.UUID,
    season_id: uuid.UUID | None,
    tx_type: TransactionType,
    team: Team,
    player: Player,
    other_team: Team | None = None,
    other_player: Player | None = None,
) -> None:
    db.add(Transaction(
        league_id=league_id,
        season_id=season_id,
        tx_type=tx_type,
        team_id=team.id,
        team_name=team.name,
        player_name=player.name,
        player_position=player.position,
        other_team_id=other_team.id if other_team else None,
        other_team_name=other_team.name if other_team else None,
        other_player_name=other_player.name if other_player else None,
    ))


@router.get('/available', response_model=AvailableLeaguesResponse)
async def get_available_leagues(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(League))
    all_leagues = result.scalars().all()

    result = await db.execute(select(Team))
    all_teams = result.scalars().all()

    teams_by_league: dict[uuid.UUID, list[Team]] = {}
    for team in all_teams:
        teams_by_league.setdefault(team.league_id, []).append(team)

    available = []
    for league in all_leagues:
        league_teams = teams_by_league.get(league.id, [])
        open_count   = sum(1 for t in league_teams if t.coach_id is None)
        if open_count > 0:
            human_count = sum(1 for t in league_teams if t.coach_id is not None)
            available.append(LeagueAvailableItem(
                id=league.id,
                name=league.name,
                human_coach_count=human_count,
                open_team_count=open_count,
            ))

    if not available:
        new_league = await create_league(db, f'League {len(all_leagues) + 1}')
        available.append(LeagueAvailableItem(
            id=new_league.id,
            name=new_league.name,
            human_coach_count=0,
            open_team_count=16,
        ))

    available.sort(key=lambda x: -x.human_coach_count)
    return AvailableLeaguesResponse(leagues=available)


@router.post('', response_model=LeagueResponse, status_code=201)
async def new_league(
    body: LeagueCreateRequest,
    db: AsyncSession = Depends(get_db),
    coach: Coach = Depends(get_current_coach),
):
    try:
        league = await create_league(db, body.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return league


@router.get('/{league_id}', response_model=LeagueDetailResponse)
async def get_league(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    league = await db.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail='League not found')

    # Active season (regular or playoffs)
    result = await db.execute(
        select(Season).where(
            Season.league_id == league_id,
            Season.status    != SeasonStatus.complete,
        )
    )
    active_season = result.scalar_one_or_none()

    # Latest season (for offseason countdown)
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    latest_season = result.scalar_one_or_none()

    # While a phase is still active, the next cron tick is what advances it, so the
    # countdown should never read 0 ("happening now") — clamp to 1 ("tomorrow") until
    # the cron actually flips the status. Timing of the cron then never matters.
    offseason_days_remaining = None
    if league.status == LeagueStatus.offseason and latest_season and latest_season.completed_at:
        elapsed = (datetime.now(timezone.utc) - latest_season.completed_at).days
        offseason_days_remaining = max(1, OFFSEASON_DAYS - elapsed)

    preseason_days_remaining = None
    if league.status == LeagueStatus.preseason and latest_season and latest_season.completed_at:
        elapsed = (datetime.now(timezone.utc) - latest_season.completed_at).days
        preseason_days_remaining = max(1, OFFSEASON_DAYS + PRESEASON_DAYS - elapsed)

    season_status = None
    if league.status == LeagueStatus.offseason:
        season_status = 'offseason'
    elif league.status == LeagueStatus.preseason:
        season_status = 'preseason'
    elif active_season:
        season_status = active_season.status.value

    return LeagueDetailResponse(
        id=league.id,
        name=league.name,
        status=league.status,
        current_week=active_season.current_week if active_season else None,
        season_status=season_status,
        created_at=league.created_at,
        offseason_days_remaining=offseason_days_remaining,
        preseason_days_remaining=preseason_days_remaining,
    )


@router.get('/{league_id}/teams', response_model=list[TeamResponse])
async def get_teams(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.league_id == league_id))
    return result.scalars().all()


@router.get('/{league_id}/teams/available', response_model=list[TeamPickerItem])
async def get_available_teams(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team).where(
            Team.league_id == league_id,
            Team.coach_id.is_(None),
        ).order_by(Team.conference, Team.division, Team.name)
    )
    return result.scalars().all()


@router.patch('/{league_id}/teams/{team_id}', response_model=TeamResponse)
async def rename_team(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      TeamRenameRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name cannot be empty')

    result = await db.execute(
        select(func.count()).where(
            Team.league_id == league_id,
            Team.name      == name,
            Team.id        != team_id,
        )
    )
    if result.scalar() > 0:
        raise HTTPException(status_code=409, detail='That name is already taken in this league')

    team.name = name
    await db.commit()
    return team


_VALID_OFF_PLANS = {'balanced', 'run_focus', 'pass_focus'}
_VALID_DEF_PLANS = {'balanced', 'run_stop', 'pass_rush'}


@router.patch('/{league_id}/teams/{team_id}/gameplan', status_code=204)
async def set_gameplan(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      GamePlanRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    if body.off_gameplan not in _VALID_OFF_PLANS:
        raise HTTPException(status_code=400, detail='Invalid offensive game plan')
    if body.def_gameplan not in _VALID_DEF_PLANS:
        raise HTTPException(status_code=400, detail='Invalid defensive game plan')

    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    team.off_gameplan = body.off_gameplan
    team.def_gameplan = body.def_gameplan
    await db.commit()


@router.post('/{league_id}/teams/{team_id}/claim', response_model=TeamResponse)
async def claim_team(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id:
        raise HTTPException(status_code=404, detail='Team not found')
    if team.coach_id is not None:
        raise HTTPException(status_code=409, detail='Team already claimed')

    team.coach_id = coach.id
    team.is_cpu   = False
    await db.commit()
    return team


@router.get('/{league_id}/teams/{team_id}/roster', response_model=list[PlayerRosterItem])
async def get_roster(league_id: uuid.UUID, team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Player)
        .where(Player.team_id == team_id)
        .order_by(Player.position, Player.composite.desc())
    )
    items = []
    for p in result.scalars().all():
        stat_names = POSITION_STATS.get(p.position, [])
        stat_dict  = dict(zip(stat_names, p.stats))
        ordered    = _reorder_stats(stat_names)
        items.append(PlayerRosterItem(
            id=p.id,
            name=p.name,
            position=p.position,
            age=p.age,
            composite=p.composite,
            ceiling_label=assign_ceiling_label(p.composite, p.potential, p.id),
            named_stats={name: stat_dict[name] for name in ordered},
            injury_games_remaining=p.injury_games_remaining,
            on_ir=p.on_ir,
        ))
    return items


@router.get('/{league_id}/teams/{team_id}/scout', response_model=list[PlayerScoutItem])
async def scout_team(league_id: uuid.UUID, team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Player)
        .where(Player.team_id == team_id)
        .order_by(Player.position, Player.composite.desc())
    )
    return _to_scout_items(result.scalars().all())


@router.get('/{league_id}/free-agents', response_model=list[PlayerScoutItem])
async def get_free_agents(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Player)
        .where(Player.league_id == league_id, Player.team_id.is_(None), Player.retired == False)  # noqa: E712
        .order_by(Player.position)
    )
    items = _to_scout_items(result.scalars().all())
    items.sort(key=lambda x: (x.position, _LABEL_ORDER.get(x.composite_label, 99), x.name))
    return items


# ============================================================
# TRAINING  (v3 progression — see training_and_potential.md)
# ============================================================

def _training_message(outcome: str, name: str, stat_changed, injury_games: int) -> str:
    if outcome == 'upgrade':
        return f'{name} looked sharp in practice — {stat_changed} is up.'
    if outcome == 'decline':
        return f'{name} struggled in a drill and lost some confidence.'
    if outcome == 'injury':
        wk = 'week' if injury_games == 1 else 'weeks'
        return f'{name} got dinged up in a hard session — out {injury_games} {wk}.'
    return f'{name} put in a solid week of work; no notable change.'


async def _latest_season(db: AsyncSession, league_id: uuid.UUID) -> Season | None:
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get('/{league_id}/teams/{team_id}/training', response_model=TrainingStateResponse)
async def get_training_state(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    season       = await _latest_season(db, league_id)
    in_regular   = bool(season and season.status == SeasonStatus.regular)
    current_week = season.current_week if season else 0

    result = await db.execute(
        select(Player)
        .where(Player.team_id == team_id, Player.retired == False)  # noqa: E712
        .order_by(Player.position, Player.composite.desc())
    )
    items = []
    for p in result.scalars().all():
        stat_names = POSITION_STATS.get(p.position, [])
        stat_dict  = dict(zip(stat_names, p.stats))
        ordered    = _reorder_stats(stat_names)
        used = p.train_sessions_used
        items.append(TrainingPlayerItem(
            id=p.id,
            name=p.name,
            position=p.position,
            age=p.age,
            composite=p.composite,
            named_stats={name: stat_dict[name] for name in ordered},
            train_sessions_used=used,
            sessions_remaining=max(0, TRAIN_SESSIONS_PER_PLAYER - used),
            trained_this_week=bool(in_regular and p.trained_in_week == current_week),
            injury_games_remaining=p.injury_games_remaining,
        ))

    return TrainingStateResponse(
        train_points=team.train_points,
        current_week=current_week,
        in_regular_season=in_regular,
        sessions_per_player=TRAIN_SESSIONS_PER_PLAYER,
        players=items,
    )


@router.post('/{league_id}/teams/{team_id}/train', response_model=TrainResultResponse)
async def train_player(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      TrainRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    season = await _latest_season(db, league_id)
    if not season or season.status != SeasonStatus.regular:
        raise HTTPException(status_code=409, detail='Training is only available during the regular season')

    points = body.points
    if points < 1 or points > MAX_TRAIN_POINTS_PER_SESSION:
        raise HTTPException(status_code=400, detail=f'Points must be between 1 and {MAX_TRAIN_POINTS_PER_SESSION}')
    if points > team.train_points:
        raise HTTPException(status_code=400, detail='Not enough training points this week')

    player = await db.get(Player, body.player_id)
    if not player or player.team_id != team_id or player.retired:
        raise HTTPException(status_code=404, detail='Player not on your roster')
    if player.injury_games_remaining > 0 or player.on_ir:
        raise HTTPException(status_code=409, detail='Player is injured and cannot train')
    if player.train_sessions_used >= TRAIN_SESSIONS_PER_PLAYER:
        raise HTTPException(status_code=409, detail='Player has no training sessions left this season')
    if player.trained_in_week == season.current_week:
        raise HTTPException(status_code=409, detail='Player already trained this week')

    result = resolve_training_session(
        stats=player.stats,
        composite=player.composite,
        potential=player.potential,
        position=player.position,
        age=player.age,
        intensity=points,
    )

    player.stats     = list(result.stats)
    player.composite = result.composite
    if result.outcome == 'injury':
        player.injury_games_remaining = result.injury_games
        player.on_ir                  = True   # frees the active slot, like a game injury
    player.train_sessions_used += 1
    player.trained_in_week      = season.current_week
    team.train_points          -= points
    await db.commit()

    return TrainResultResponse(
        outcome=result.outcome,
        message=_training_message(result.outcome, player.name, result.stat_changed, result.injury_games),
        stat_changed=result.stat_changed,
        delta=result.delta,
        composite=result.composite,
        injury_games=result.injury_games,
        train_points=team.train_points,
        train_sessions_used=player.train_sessions_used,
        sessions_remaining=max(0, TRAIN_SESSIONS_PER_PLAYER - player.train_sessions_used),
    )


_POSITION_MAX_ACTIVE = {
    'QB': 2, 'WR': 5, 'TE': 2, 'RB': 3, 'OL': 6,
    'DT': 4, 'DE': 4, 'LB': 5, 'CB': 4, 'S': 4,
    'K': 1, 'P': 1,
}


@router.post('/{league_id}/teams/{team_id}/sign-fa', status_code=204)
async def sign_free_agent(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      SignFARequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    player = await db.get(Player, body.player_id)
    if not player or player.league_id != league_id or player.team_id is not None or player.retired:
        raise HTTPException(status_code=404, detail='Player not available')

    result = await db.execute(
        select(func.count()).where(
            Player.team_id  == team_id,
            Player.on_ir    == False,  # noqa: E712
            Player.position == player.position,
        )
    )
    active_at_pos = result.scalar()
    drop = None
    if active_at_pos >= _POSITION_MAX_ACTIVE.get(player.position, 0):
        if body.drop_player_id is None:
            raise HTTPException(status_code=409, detail=f'No open {player.position} slot on active roster')
        drop = await db.get(Player, body.drop_player_id)
        if not drop or drop.team_id != team_id or drop.on_ir or drop.position != player.position:
            raise HTTPException(status_code=400, detail=f'Must drop an active {player.position} to make room')
        drop.team_id = None
        drop.on_ir   = False

    player.team_id = team_id
    player.on_ir   = False
    season_id = await _current_season_id(db, league_id)
    await _write_tx(db, league_id, season_id, TransactionType.sign, team, player,
                    other_player=drop if drop is not None else None)
    await db.commit()


@router.post('/{league_id}/teams/{team_id}/activate', status_code=204)
async def activate_ir_player(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      ActivateRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    activate = await db.get(Player, body.activate_player_id)
    if not activate or activate.team_id != team_id or not activate.on_ir:
        raise HTTPException(status_code=400, detail='Activate player must be on IR on your roster')
    if activate.injury_games_remaining > 0:
        raise HTTPException(status_code=400, detail='Player not yet recovered')

    if body.drop_player_id is None:
        result = await db.execute(
            select(func.count()).where(
                Player.team_id  == team_id,
                Player.on_ir    == False,   # noqa: E712
                Player.position == activate.position,
            )
        )
        if result.scalar() >= _POSITION_MAX_ACTIVE.get(activate.position, 0):
            raise HTTPException(status_code=409,
                detail=f'Position full — drop an active {activate.position} to activate')
    else:
        drop = await db.get(Player, body.drop_player_id)
        if not drop or drop.team_id != team_id or drop.on_ir:
            raise HTTPException(status_code=400, detail='Drop player must be active on your roster')
        if drop.position != activate.position:
            raise HTTPException(status_code=400,
                detail=f'Must drop a {activate.position} to activate a {activate.position}')
        drop.team_id = None
        drop.on_ir   = False

    activate.on_ir = False
    season_id = await _current_season_id(db, league_id)
    await _write_tx(db, league_id, season_id, TransactionType.activate, team, activate,
                    other_player=drop if body.drop_player_id else None)
    await db.commit()


@router.post('/{league_id}/teams/{team_id}/release', response_model=ReleaseResponse)
async def release_player(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      ReleaseRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    player = await db.get(Player, body.player_id)
    if not player or player.team_id != team_id:
        raise HTTPException(status_code=400, detail='Player not on your team')

    # Enforce starter floor — can't release below the minimum active count for the position
    if not player.on_ir:
        min_active = _POSITION_STARTERS.get(player.position, 1)
        result = await db.execute(
            select(func.count()).where(
                Player.team_id  == team_id,
                Player.on_ir    == False,  # noqa: E712
                Player.position == player.position,
            )
        )
        if result.scalar() <= min_active:
            raise HTTPException(
                status_code=409,
                detail=f'Cannot release — minimum {min_active} active {player.position} required',
            )

    player.team_id = None
    player.on_ir   = False
    await db.flush()

    thin = []
    for pos, max_count in _POSITION_MAX_ACTIVE.items():
        result = await db.execute(
            select(func.count()).where(
                Player.team_id  == team_id,
                Player.on_ir    == False,  # noqa: E712
                Player.position == pos,
            )
        )
        if result.scalar() < max_count:
            thin.append(pos)

    season_id = await _current_season_id(db, league_id)
    await _write_tx(db, league_id, season_id, TransactionType.release, team, player)
    await db.commit()
    return ReleaseResponse(thin_positions=thin)


_TRADE_TOLERANCE   = 5
_TRADE_REJECT_RATE = 0.20


@router.post('/{league_id}/teams/{team_id}/trade', response_model=TradeResponse)
async def request_trade(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    body:      TradeRequest,
    db:        AsyncSession = Depends(get_db),
    coach:     Coach        = Depends(get_current_coach),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id or team.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='Not your team')

    my_player = await db.get(Player, body.my_player_id)
    if not my_player or my_player.team_id != team_id:
        raise HTTPException(status_code=400, detail='Player not on your team')
    if my_player.on_ir:
        raise HTTPException(status_code=400, detail='Cannot trade a player on IR')

    their_player = await db.get(Player, body.their_player_id)
    if not their_player or their_player.league_id != league_id or their_player.team_id is None:
        raise HTTPException(status_code=400, detail='Player not found')
    if their_player.on_ir:
        raise HTTPException(status_code=400, detail='That player is on IR')

    cpu_team = await db.get(Team, their_player.team_id)
    if not cpu_team or not cpu_team.is_cpu:
        raise HTTPException(status_code=400, detail='Can only trade with CPU teams')

    delta = my_player.composite - their_player.composite
    if delta < -_TRADE_TOLERANCE:
        return TradeResponse(accepted=False, reason='Not enough value in your offer')

    if random.random() < _TRADE_REJECT_RATE:
        return TradeResponse(accepted=False, reason='Not interested at this time')

    my_player.team_id    = their_player.team_id
    their_player.team_id = team_id
    season_id = await _current_season_id(db, league_id)
    await _write_tx(db, league_id, season_id, TransactionType.trade, team, my_player, other_team=cpu_team, other_player=their_player)
    await db.commit()
    return TradeResponse(accepted=True, reason='Trade accepted')


_LABEL_ORDER  = {'Elite': 0, 'Above Avg': 1, 'Average': 2, 'Below Avg': 3, 'Weak': 4}
# Fitness stats are shared across positions and always render at the bottom in a
# fixed order, so their placement can't hint at what the engine values per position.
_FITNESS_ORDER = ['SPEED', 'AGILITY', 'STAMINA', 'STRENGTH']
_FITNESS_STATS = frozenset(_FITNESS_ORDER)


def _reorder_stats(stat_names: list[str]) -> list[str]:
    if len(stat_names) <= 1:
        return list(stat_names)
    skill   = stat_names[0]
    rest    = stat_names[1:]
    unique  = sorted(s for s in rest if s not in _FITNESS_STATS)
    fitness = [s for s in _FITNESS_ORDER if s in rest]
    return [skill] + unique + fitness


def _to_scout_items(players) -> list[PlayerScoutItem]:
    items = []
    for p in players:
        stat_names = POSITION_STATS.get(p.position, [])
        stat_dict  = dict(zip(stat_names, p.stats))
        ordered    = _reorder_stats(stat_names)
        items.append(PlayerScoutItem(
            id=p.id,
            name=p.name,
            position=p.position,
            age=p.age,
            composite_label=assign_label(p.composite),
            named_stat_labels={name: assign_label(stat_dict[name]) for name in ordered},
            injury_games_remaining=p.injury_games_remaining,
        ))
    return items


@router.get('/{league_id}/schedule', response_model=list[GameResponse])
async def get_schedule(
    league_id: uuid.UUID,
    week: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail='No season found')

    q = select(Game).where(Game.season_id == season.id)
    if week is not None:
        q = q.where(Game.week == week)

    result = await db.execute(q.order_by(Game.week))
    return result.scalars().all()


@router.get('/{league_id}/games/{game_id}', response_model=GameDetailResponse)
async def get_game_detail(
    league_id: uuid.UUID,
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
    )
    game = result.scalar_one_or_none()
    if not game or game.home_team.league_id != league_id:
        raise HTTPException(status_code=404, detail='Game not found')

    result = await db.execute(
        select(PlayerGameStats)
        .where(PlayerGameStats.game_id == game_id)
        .options(selectinload(PlayerGameStats.player))
    )
    stat_rows = result.scalars().all()

    home_stats, away_stats = [], []
    for row in stat_rows:
        line = PlayerStatLine(
            player_id=row.player_id,
            player_name=row.player.name,
            position=row.player.position,
            pass_attempts=row.pass_attempts,
            pass_completions=row.pass_completions,
            pass_yards=row.pass_yards,
            pass_tds=row.pass_tds,
            interceptions_thrown=row.interceptions_thrown,
            rush_attempts=row.rush_attempts,
            rush_yards=row.rush_yards,
            rush_tds=row.rush_tds,
            receptions=row.receptions,
            receiving_yards=row.receiving_yards,
            receiving_tds=row.receiving_tds,
            fumbles=row.fumbles,
            fumbles_lost=row.fumbles_lost,
            sacks_allowed=row.sacks_allowed,
            tackles=row.tackles,
            sacks=row.sacks,
            interceptions=row.interceptions,
            forced_fumbles=row.forced_fumbles,
            fumble_recoveries=row.fumble_recoveries,
        )
        if row.team_id == game.home_team_id:
            home_stats.append(line)
        else:
            away_stats.append(line)

    return GameDetailResponse(
        id=game.id,
        week=game.week,
        is_playoff=game.is_playoff,
        home_team_id=game.home_team_id,
        home_team_name=game.home_team.name,
        home_score=game.home_score,
        away_team_id=game.away_team_id,
        away_team_name=game.away_team.name,
        away_score=game.away_score,
        status=game.status,
        played_at=game.played_at,
        home_stats=home_stats,
        away_stats=away_stats,
        scoring_plays=game.scoring_plays,
    )


_POSITION_STARTERS = {
    'QB': 1, 'WR': 3, 'TE': 1, 'RB': 1, 'OL': 5,
    'DT': 2, 'DE': 2, 'LB': 3, 'CB': 2, 'S': 2,
    'K': 1, 'P': 1,
}


def _compute_team_groups(players: list) -> dict[str, GroupComposite]:
    by_pos: dict[str, list[float]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p.composite)
    for pos in by_pos:
        by_pos[pos].sort(reverse=True)

    groups: dict[str, GroupComposite] = {}
    for pos, starter_count in _POSITION_STARTERS.items():
        composites = by_pos.get(pos, [])
        if not composites:
            continue
        starters = composites[:starter_count]
        backup = composites[starter_count:starter_count + 1]
        starter_avg = sum(starters) / len(starters)
        group_comp = round(0.80 * starter_avg + 0.20 * backup[0], 1) if backup else round(starter_avg, 1)
        label = assign_label(round(group_comp)) or 'Average'
        groups[pos] = GroupComposite(composite=group_comp, label=label)
    return groups


@router.get('/{league_id}/games/{game_id}/matchup', response_model=GameMatchupResponse)
async def get_game_matchup(
    league_id: uuid.UUID,
    game_id:   uuid.UUID,
    db:        AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
    )
    game = result.scalar_one_or_none()
    if not game or game.home_team.league_id != league_id:
        raise HTTPException(status_code=404, detail='Game not found')

    home_id = game.home_team_id
    away_id = game.away_team_id

    result = await db.execute(
        select(Player).where(Player.team_id.in_([home_id, away_id]))
    )
    all_players = result.scalars().all()
    home_players = [p for p in all_players if p.team_id == home_id]
    away_players = [p for p in all_players if p.team_id == away_id]

    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()

    records: dict[uuid.UUID, dict] = {
        home_id: {'wins': 0, 'losses': 0, 'ties': 0},
        away_id: {'wins': 0, 'losses': 0, 'ties': 0},
    }
    if season:
        result = await db.execute(
            select(Game).where(
                Game.season_id == season.id,
                Game.status == GameStatus.complete,
                Game.is_playoff == False,  # noqa: E712
                or_(
                    Game.home_team_id.in_([home_id, away_id]),
                    Game.away_team_id.in_([home_id, away_id]),
                ),
            )
        )
        for g in result.scalars().all():
            if g.home_score > g.away_score:
                if g.home_team_id in records:
                    records[g.home_team_id]['wins'] += 1
                if g.away_team_id in records:
                    records[g.away_team_id]['losses'] += 1
            elif g.away_score > g.home_score:
                if g.away_team_id in records:
                    records[g.away_team_id]['wins'] += 1
                if g.home_team_id in records:
                    records[g.home_team_id]['losses'] += 1
            else:
                if g.home_team_id in records:
                    records[g.home_team_id]['ties'] += 1
                if g.away_team_id in records:
                    records[g.away_team_id]['ties'] += 1

    return GameMatchupResponse(
        game_id=game.id,
        week=game.week,
        is_playoff=game.is_playoff,
        home_team=TeamMatchupSide(
            team_id=home_id,
            name=game.home_team.name,
            wins=records[home_id]['wins'],
            losses=records[home_id]['losses'],
            ties=records[home_id]['ties'],
            groups=_compute_team_groups(home_players),
            off_gameplan=game.home_team.off_gameplan,
            def_gameplan=game.home_team.def_gameplan,
        ),
        away_team=TeamMatchupSide(
            team_id=away_id,
            name=game.away_team.name,
            wins=records[away_id]['wins'],
            losses=records[away_id]['losses'],
            ties=records[away_id]['ties'],
            groups=_compute_team_groups(away_players),
            off_gameplan=game.away_team.off_gameplan,
            def_gameplan=game.away_team.def_gameplan,
        ),
    )


@router.get('/{league_id}/standings', response_model=StandingsResponse)
async def get_standings(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail='No season found')

    result = await db.execute(select(Team).where(Team.league_id == league_id))
    teams = result.scalars().all()

    rows: dict[uuid.UUID, dict] = {
        t.id: {
            'team_id': t.id,
            'name': t.name,
            'conference': t.conference,
            'division': t.division,
            'wins': 0,
            'losses': 0,
            'ties': 0,
            'points_for': 0,
            'points_against': 0,
        }
        for t in teams
    }

    result = await db.execute(
        select(Game).where(
            Game.season_id == season.id,
            Game.status == GameStatus.complete,
            Game.is_playoff == False,
        )
    )
    for g in result.scalars().all():
        home = rows[g.home_team_id]
        away = rows[g.away_team_id]
        home['points_for'] += g.home_score
        home['points_against'] += g.away_score
        away['points_for'] += g.away_score
        away['points_against'] += g.home_score
        if g.home_score > g.away_score:
            home['wins'] += 1
            away['losses'] += 1
        elif g.away_score > g.home_score:
            away['wins'] += 1
            home['losses'] += 1
        else:
            home['ties'] += 1
            away['ties'] += 1

    standing_list = [
        StandingRow(**r, point_differential=r['points_for'] - r['points_against'])
        for r in rows.values()
    ]
    standing_list.sort(key=lambda r: (r.conference, r.division, -r.wins, -r.point_differential))

    return StandingsResponse(standings=standing_list)


# Stat fields shared between YTD aggregation and career accumulation
_STAT_FIELDS = [
    'pass_attempts', 'pass_completions', 'pass_yards', 'pass_tds', 'interceptions_thrown',
    'rush_attempts', 'rush_yards', 'rush_tds',
    'receptions', 'receiving_yards', 'receiving_tds',
    'fumbles', 'fumbles_lost', 'sacks_allowed',
    'tackles', 'sacks', 'interceptions', 'forced_fumbles', 'fumble_recoveries',
]


@router.get('/{league_id}/players/{player_id}/stats', response_model=PlayerStatsResponse)
async def get_player_stats(
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail='Player not found')

    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()

    ytd: dict[str, int] = {f: 0 for f in _STAT_FIELDS}
    if season:
        agg = await db.execute(
            select(*[
                func.coalesce(func.sum(getattr(PlayerGameStats, f)), 0).label(f)
                for f in _STAT_FIELDS
            ])
            .join(Game, PlayerGameStats.game_id == Game.id)
            .where(
                PlayerGameStats.player_id == player_id,
                Game.season_id == season.id,
            )
        )
        row = agg.one_or_none()
        if row:
            ytd = {f: getattr(row, f) for f in _STAT_FIELDS}

    return PlayerStatsResponse(
        ytd=ytd,
        career={f: int(player.career_stats.get(f, 0)) for f in _STAT_FIELDS},
    )


_UPSET_THRESHOLDS = [(4, 4), (8, 6), (12, 8), (17, 10)]


def _upset_delta(week: int) -> int:
    for max_week, delta in _UPSET_THRESHOLDS:
        if week <= max_week:
            return delta
    return 10


@router.get('/{league_id}/teams/{team_id}/news', response_model=TeamNewsResponse)
async def get_team_news(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    db:        AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    team   = await db.get(Team, team_id)
    if not season or not team:
        return TeamNewsResponse(headline=f'No news yet.')

    # All completed games for this team this season, oldest first
    result = await db.execute(
        select(Game)
        .where(
            Game.season_id == season.id,
            Game.status    == GameStatus.complete,
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
        )
        .order_by(Game.week)
    )
    completed = result.scalars().all()

    if not completed:
        return TeamNewsResponse(headline=f'{team.name} are preparing for their first game of the season.')

    # Record + result sequence
    wins = losses = ties = 0
    seq  = []
    for g in completed:
        home    = g.home_team_id == team_id
        my_s    = g.home_score if home else g.away_score
        opp_s   = g.away_score if home else g.home_score
        if my_s > opp_s:
            wins  += 1; seq.append('W')
        elif opp_s > my_s:
            losses += 1; seq.append('L')
        else:
            ties  += 1; seq.append('T')

    # Streak
    streak_type  = seq[-1]
    streak_count = 0
    for r in reversed(seq):
        if r == streak_type:
            streak_count += 1
        else:
            break

    # Last game
    last   = completed[-1]
    last_r = seq[-1]
    home   = last.home_team_id == team_id
    opp_id = last.away_team_id if home else last.home_team_id
    my_s   = last.home_score if home else last.away_score
    opp_s  = last.away_score if home else last.home_score
    score_str = f'{my_s}–{opp_s}'

    opp_team = await db.get(Team, opp_id)
    opp_name = opp_team.name if opp_team else 'the opponent'

    # Star performer from last game
    result = await db.execute(
        select(PlayerGameStats)
        .where(
            PlayerGameStats.game_id == last.id,
            PlayerGameStats.team_id == team_id,
        )
        .options(selectinload(PlayerGameStats.player))
    )
    stats     = result.scalars().all()
    star_line = None
    best_score = 0
    for s in stats:
        cand, score = None, 0
        if s.pass_tds >= 3:
            cand  = f'{s.player.name} threw for {s.pass_yards} yards and {s.pass_tds} TDs'
            score = s.pass_tds * 10 + s.pass_yards // 10
        elif s.interceptions >= 2:
            cand  = f'{s.player.name} picked off {s.interceptions} passes'
            score = s.interceptions * 15
        elif s.rush_yards >= 130:
            cand  = f'{s.player.name} rushed for {s.rush_yards} yards'
            score = s.rush_yards
        elif s.receiving_yards >= 130:
            cand  = f'{s.player.name} hauled in {s.receiving_yards} receiving yards'
            score = s.receiving_yards
        elif s.sacks >= 2:
            cand  = f'{s.player.name} recorded {s.sacks} sacks'
            score = s.sacks * 20
        elif s.tackles >= 10:
            cand  = f'{s.player.name} racked up {s.tackles} tackles'
            score = s.tackles
        if cand and score > best_score:
            star_line  = cand
            best_score = score

    # Elite player on IR
    result = await db.execute(
        select(Player).where(
            Player.team_id == team_id,
            Player.on_ir   == True,  # noqa: E712
        )
    )
    ir_elite = next(
        (p for p in result.scalars().all() if assign_label(p.composite) == 'Elite'),
        None,
    )

    # Opponent pre-game record (for upset detection)
    opp_wins_before = 0
    if not last.is_playoff:
        result = await db.execute(
            select(Game).where(
                Game.season_id == season.id,
                Game.status    == GameStatus.complete,
                Game.id        != last.id,
                or_(Game.home_team_id == opp_id, Game.away_team_id == opp_id),
            )
        )
        for g in result.scalars().all():
            oh = g.home_team_id == opp_id
            if (g.home_score if oh else g.away_score) > (g.away_score if oh else g.home_score):
                opp_wins_before += 1

    # ── Assemble candidates ──────────────────────────────────────────────────
    # Priority 2 = playoff milestone (always wins)
    # Priority 1 = all other interesting events (random among tied)
    # Priority 0 = generic fallback
    candidates: list[tuple[int, str]] = []
    name = team.name

    # Playoff milestones
    played_playoff = any(g.is_playoff for g in completed)

    # Determine if this team has any playoff game scheduled or played
    team_in_playoffs = False
    if season.status in (SeasonStatus.playoffs, SeasonStatus.complete):
        _r = await db.execute(
            select(func.count()).select_from(Game)
            .where(
                Game.season_id == season.id,
                Game.is_playoff == True,  # noqa: E712
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            )
        )
        team_in_playoffs = (_r.scalar() or 0) > 0

    if season.status == SeasonStatus.complete:
        # Season's over: reveal the champion to everyone. This supersedes any stale
        # elimination headline for a team whose own playoff run ended earlier.
        _r = await db.execute(
            select(Game)
            .where(Game.season_id == season.id, Game.week == PLAYOFF_LEAGUE_CHAMP, Game.status == GameStatus.complete)  # noqa: E712
            .options(selectinload(Game.home_team), selectinload(Game.away_team))
        )
        _cg = _r.scalar_one_or_none()
        if _cg:
            _w = _cg.home_team if _cg.home_score > _cg.away_score else _cg.away_team
            if _w.id == team_id:
                candidates.append((2, f'The {name} are CHAMPIONS! What a season to remember.'))
            elif team_in_playoffs:
                candidates.append((2, f'{_w.name} won it all. {name} made a playoff run but came up short — time to reload.'))
            else:
                candidates.append((2, f'{_w.name} won the championship this season. Time to reload, {name}.'))
    elif season.status == SeasonStatus.playoffs and team_in_playoffs and not played_playoff:
        candidates.append((2, f'{name} have punched their ticket to the playoffs!'))
    elif season.status == SeasonStatus.playoffs and not team_in_playoffs:
        # Spectator mode — show league-wide playoff coverage
        _r = await db.execute(
            select(Game)
            .where(Game.season_id == season.id, Game.is_playoff == True, Game.status == GameStatus.complete)  # noqa: E712
            .options(selectinload(Game.home_team), selectinload(Game.away_team))
            .order_by(Game.week.desc())
        )
        _pf = _r.scalars().all()
        if _pf:
            _latest = max(g.week for g in _pf)
            if _latest == PLAYOFF_LEAGUE_CHAMP:
                _cg = next(g for g in _pf if g.week == PLAYOFF_LEAGUE_CHAMP)
                _w = _cg.home_team if _cg.home_score > _cg.away_score else _cg.away_team
                candidates.append((2, f'The {_w.name} are champions! {name} watches the celebration from home.'))
            elif _latest == PLAYOFF_CONF_CHAMP:
                _fin = [g.home_team if g.home_score > g.away_score else g.away_team for g in _pf if g.week == PLAYOFF_CONF_CHAMP]
                if len(_fin) == 2:
                    candidates.append((2, f'{_fin[0].name} and {_fin[1].name} will meet in the Championship Game.'))
                elif len(_fin) == 1:
                    candidates.append((2, f'{_fin[0].name} have advanced to the Championship Game.'))
            elif _latest == PLAYOFF_DIVISIONAL:
                candidates.append((2, f'The conference championships are set. {name} watches the playoffs from home.'))
        else:
            candidates.append((1, f"{name} missed the playoffs this year. Time to build for next season."))
    elif last.is_playoff:
        w = last.week
        if   last_r == 'W' and w == PLAYOFF_LEAGUE_CHAMP:
            candidates.append((2, f'The {name} are CHAMPIONS! What a season to remember.'))
        elif last_r == 'L' and w == PLAYOFF_LEAGUE_CHAMP:
            candidates.append((2, f'{name} came so close — a heartbreaking championship loss ends the run.'))
        elif last_r == 'W' and w == PLAYOFF_CONF_CHAMP:
            candidates.append((2, f'{name} are headed to the Championship Game!'))
        elif last_r == 'L' and w == PLAYOFF_CONF_CHAMP:
            candidates.append((2, f'Heartbreak for {name} — they fall just short of the Championship Game.'))
        elif last_r == 'W' and w == PLAYOFF_DIVISIONAL:
            candidates.append((2, f'{name} keep the championship dream alive with a first-round win.'))
        elif last_r == 'L' and w == PLAYOFF_DIVISIONAL:
            candidates.append((2, f"{name}'s season ends with a first-round playoff exit."))

    # Streak
    if streak_count >= 3 and streak_type == 'W':
        candidates.append((1, f'{name} have won {streak_count} straight. This team is building real momentum.'))
    elif streak_count >= 3 and streak_type == 'L':
        candidates.append((1, f'{name} have lost {streak_count} in a row. Fans are growing restless.'))

    # Upset
    if not last.is_playoff:
        my_wins_before = wins - (1 if last_r == 'W' else 0)
        threshold = _upset_delta(last.week)
        if last_r == 'L' and (my_wins_before - opp_wins_before) >= threshold:
            candidates.append((1, f'Shocking upset — {opp_name} knock off {name} in one of the week\'s biggest surprises.'))
        elif last_r == 'W' and (opp_wins_before - my_wins_before) >= threshold:
            candidates.append((1, f'{name} pull off one of the season\'s biggest upsets, beating {opp_name}.'))

    # Star performer
    if star_line:
        result_word = 'a win' if last_r == 'W' else 'a loss' if last_r == 'L' else 'a tie'
        candidates.append((1, f'{star_line} in {result_word} against {opp_name}.'))

    # Elite injury
    if ir_elite:
        candidates.append((1, f'{name} are devastated as {ir_elite.name} ({ir_elite.position}) heads to injured reserve.'))

    # Generic fallback
    record_str = f'{wins}–{losses}–{ties}' if ties > 0 else f'{wins}–{losses}'
    if last_r == 'W':
        candidates.append((0, f'{name} pick up a win against {opp_name} ({score_str}), improving to {record_str}.'))
    elif last_r == 'L':
        margin = opp_s - my_s
        if margin <= 4:
            candidates.append((0, f'{name} fell just short against {opp_name}, losing {score_str}.'))
        else:
            candidates.append((0, f'{name} dropped a {score_str} game to {opp_name}, falling to {record_str}.'))
    else:
        candidates.append((0, f'{name} and {opp_name} played to a {score_str} draw.'))

    top_priority = max(p for p, _ in candidates)
    top = [h for p, h in candidates if p == top_priority]
    return TeamNewsResponse(headline=random.choice(top))


@router.get('/{league_id}/teams/{team_id}/history', response_model=TeamHistoryResponse)
async def get_team_history(
    league_id: uuid.UUID,
    team_id:   uuid.UUID,
    db:        AsyncSession = Depends(get_db),
):
    team = await db.get(Team, team_id)
    if not team or team.league_id != league_id:
        raise HTTPException(status_code=404, detail='Team not found')

    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id, Season.status == SeasonStatus.complete)
        .order_by(Season.season_number.asc())
    )
    seasons = result.scalars().all()

    entries = []
    for season in seasons:
        result = await db.execute(
            select(Game)
            .where(
                Game.season_id == season.id,
                Game.status    == GameStatus.complete,
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            )
        )
        games = result.scalars().all()

        wins = losses = ties = 0
        made_playoffs = False
        playoff_wins  = 0

        for g in games:
            is_home   = g.home_team_id == team_id
            my_score  = g.home_score if is_home else g.away_score
            opp_score = g.away_score if is_home else g.home_score
            if g.is_playoff:
                made_playoffs = True
                if my_score is not None and opp_score is not None and my_score > opp_score:
                    playoff_wins += 1
            else:
                if my_score is None or opp_score is None:
                    continue
                if my_score > opp_score:
                    wins += 1
                elif my_score < opp_score:
                    losses += 1
                else:
                    ties += 1

        if not made_playoffs:
            playoff_result = 'missed'
        elif playoff_wins == 0:
            playoff_result = 'first_round'
        elif playoff_wins == 1:
            playoff_result = 'conf_champ'
        elif playoff_wins == 2:
            playoff_result = 'runner_up'
        else:
            playoff_result = 'champion'

        entries.append({'season_number': season.season_number, 'wins': wins, 'losses': losses, 'ties': ties, 'playoff_result': playoff_result})

    return TeamHistoryResponse(team_id=team_id, team_name=team.name, seasons=entries)


@router.get('/{league_id}/leaders', response_model=LeagueLeadersResponse)
async def get_league_leaders(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail='No season found')

    agg = await db.execute(
        select(
            Player.id.label('player_id'),
            Player.name.label('player_name'),
            Player.position,
            Team.name.label('team_name'),
            func.sum(PlayerGameStats.pass_yards).label('pass_yards'),
            func.sum(PlayerGameStats.pass_tds).label('pass_tds'),
            func.sum(PlayerGameStats.pass_completions).label('pass_completions'),
            func.sum(PlayerGameStats.pass_attempts).label('pass_attempts'),
            func.sum(PlayerGameStats.interceptions_thrown).label('interceptions_thrown'),
            func.sum(PlayerGameStats.rush_yards).label('rush_yards'),
            func.sum(PlayerGameStats.rush_tds).label('rush_tds'),
            func.sum(PlayerGameStats.rush_attempts).label('rush_attempts'),
            func.sum(PlayerGameStats.receiving_yards).label('receiving_yards'),
            func.sum(PlayerGameStats.receiving_tds).label('receiving_tds'),
            func.sum(PlayerGameStats.receptions).label('receptions'),
            func.sum(PlayerGameStats.tackles).label('tackles'),
            func.sum(PlayerGameStats.sacks).label('sacks'),
            func.sum(PlayerGameStats.interceptions).label('interceptions'),
            func.sum(PlayerGameStats.forced_fumbles).label('forced_fumbles'),
            func.sum(PlayerGameStats.fumble_recoveries).label('fumble_recoveries'),
        )
        .select_from(PlayerGameStats)
        .join(Game, PlayerGameStats.game_id == Game.id)
        .join(Player, PlayerGameStats.player_id == Player.id)
        .outerjoin(Team, Player.team_id == Team.id)
        .where(Game.season_id == season.id, Game.is_playoff == False)  # noqa: E712
        .group_by(Player.id, Player.name, Player.position, Team.name)
    )
    rows = agg.all()

    passing, rushing, receiving, defense = [], [], [], []
    for row in rows:
        base = dict(
            player_id=row.player_id,
            player_name=row.player_name,
            team_name=row.team_name or 'Free Agent',
            position=row.position,
        )
        if (row.pass_yards or 0) > 0:
            passing.append(PassingLeader(**base,
                pass_yards=row.pass_yards or 0,
                pass_tds=row.pass_tds or 0,
                pass_completions=row.pass_completions or 0,
                pass_attempts=row.pass_attempts or 0,
                interceptions_thrown=row.interceptions_thrown or 0,
            ))
        if (row.rush_yards or 0) > 0:
            rushing.append(RushingLeader(**base,
                rush_yards=row.rush_yards or 0,
                rush_tds=row.rush_tds or 0,
                rush_attempts=row.rush_attempts or 0,
            ))
        if (row.receiving_yards or 0) > 0:
            receiving.append(ReceivingLeader(**base,
                receiving_yards=row.receiving_yards or 0,
                receiving_tds=row.receiving_tds or 0,
                receptions=row.receptions or 0,
            ))
        def_total = sum(getattr(row, f) or 0 for f in (
            'tackles', 'sacks', 'interceptions', 'forced_fumbles', 'fumble_recoveries'
        ))
        if def_total > 0:
            defense.append(DefenseLeader(**base,
                tackles=row.tackles or 0,
                sacks=row.sacks or 0,
                interceptions=row.interceptions or 0,
                forced_fumbles=row.forced_fumbles or 0,
                fumble_recoveries=row.fumble_recoveries or 0,
            ))

    passing.sort(key=lambda x: x.pass_yards, reverse=True)
    rushing.sort(key=lambda x: x.rush_yards, reverse=True)
    receiving.sort(key=lambda x: x.receiving_yards, reverse=True)

    def_tackles = sorted(defense, key=lambda x: x.tackles, reverse=True)[:10]
    def_sacks   = sorted(
        [d for d in defense if d.sacks > 0], key=lambda x: x.sacks, reverse=True
    )[:10]
    def_ints    = sorted(
        [d for d in defense if d.interceptions > 0], key=lambda x: x.interceptions, reverse=True
    )[:10]

    return LeagueLeadersResponse(
        passing=passing[:10],
        rushing=rushing[:10],
        receiving=receiving[:10],
        def_tackles=def_tackles,
        def_sacks=def_sacks,
        def_interceptions=def_ints,
    )


# ============================================================
# DRAFT ENDPOINTS
# ============================================================

def _require_team_in_league(team):
    if not team:
        raise HTTPException(status_code=403, detail='Not in this league')


@router.get('/{league_id}/draft/class')
async def get_draft_class_endpoint(
    league_id: uuid.UUID,
    coach:     Coach = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    """Scout the current draft class (available during offseason and preseason)."""
    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    _require_team_in_league(result.scalar_one_or_none())
    return await get_draft_class(db, league_id)


@router.get('/{league_id}/draft/results')
async def get_draft_results_endpoint(
    league_id: uuid.UUID,
    coach:     Coach = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    """Full pick log for the most recent draft."""
    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    team = result.scalar_one_or_none()
    _require_team_in_league(team)
    return await get_draft_results(db, league_id, team.id)


@router.get('/{league_id}/draft/board')
async def get_draft_board(
    league_id: uuid.UUID,
    coach:     Coach = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    """Return this coach's draft board for the league."""
    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    team = result.scalar_one_or_none()
    _require_team_in_league(team)
    board = team.draft_board or {'position_priority': [None, None, None, None, None]}
    return board


@router.put('/{league_id}/draft/board')
async def set_draft_board(
    league_id: uuid.UUID,
    body:      dict,
    coach:     Coach = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    """
    Set this coach's draft board. Body: {"position_priority": ["QB", "WR", null, null, null]}
    Exactly 5 slots; each is a position string or null.
    """
    result = await db.execute(
        select(League).where(League.id == league_id)
    )
    league = result.scalar_one_or_none()
    if not league or league.status not in (LeagueStatus.offseason, LeagueStatus.preseason):
        raise HTTPException(status_code=400, detail='Board can only be set during offseason')

    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    team = result.scalar_one_or_none()
    _require_team_in_league(team)

    priority = body.get('position_priority', [])
    if len(priority) != 5:
        raise HTTPException(status_code=400, detail='position_priority must have exactly 5 slots')

    valid_positions = {'QB','WR','TE','RB','OL','DT','DE','LB','CB','S','K','P', None}
    for slot in priority:
        if slot not in valid_positions:
            raise HTTPException(status_code=400, detail=f'Invalid position: {slot}')

    player_ranking = body.get('player_ranking', [])
    if not isinstance(player_ranking, list):
        raise HTTPException(status_code=400, detail='player_ranking must be a list')

    from sqlalchemy.orm.attributes import flag_modified
    team.draft_board = {'position_priority': priority, 'player_ranking': player_ranking}
    flag_modified(team, 'draft_board')
    await db.commit()
    return team.draft_board


# ============================================================
# TRANSACTION ENDPOINTS
# ============================================================

def _encode_cursor(row) -> str:
    """Keyset cursor for any row with .created_at + .id (transactions, messages)."""
    raw = f'{row.created_at.isoformat()}|{row.id}'
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = raw.rsplit('|', 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


@router.get('/{league_id}/transactions', response_model=TransactionsPageResponse)
async def get_transactions(
    league_id: uuid.UUID,
    team_id:   uuid.UUID | None = Query(None, description='Filter to one team (matches either side of a trade)'),
    cursor:    str | None       = Query(None, description='Opaque pagination cursor from a previous page'),
    limit:     int              = Query(25, ge=1, le=100),
    coach:     Coach            = Depends(get_current_coach),
    db:        AsyncSession     = Depends(get_db),
):
    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    _require_team_in_league(result.scalar_one_or_none())

    season_id = await _current_season_id(db, league_id)

    query = (
        select(Transaction)
        .where(Transaction.league_id == league_id, Transaction.season_id == season_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
    )
    if team_id is not None:
        query = query.where(
            or_(Transaction.team_id == team_id, Transaction.other_team_id == team_id)
        )
    if cursor is not None:
        try:
            c_ts, c_id = _decode_cursor(cursor)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail='Invalid cursor')
        # Keyset: everything strictly "older" than the cursor in (created_at, id) DESC order.
        query = query.where(
            or_(
                Transaction.created_at < c_ts,
                and_(Transaction.created_at == c_ts, Transaction.id < c_id),
            )
        )

    # Fetch one extra to know whether another page exists.
    result = await db.execute(query.limit(limit + 1))
    rows = result.scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]

    return TransactionsPageResponse(
        items=[
            TransactionItem(
                tx_type=t.tx_type.value,
                team_name=t.team_name,
                player_name=t.player_name,
                player_position=t.player_position,
                other_team_name=t.other_team_name,
                other_player_name=t.other_player_name,
                created_at=t.created_at.isoformat(),
            )
            for t in page
        ],
        next_cursor=_encode_cursor(page[-1]) if has_more and page else None,
    )


# ============================================================
# LEAGUE MESSAGE BOARD  (flat feed — TODO.md "Social")
# ============================================================

async def _require_league_team(db: AsyncSession, league_id: uuid.UUID, coach: Coach) -> Team:
    """Return the caller's team in this league, or 403 if they aren't a coach here."""
    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.coach_id == coach.id)
    )
    team = result.scalar_one_or_none()
    _require_team_in_league(team)
    return team


@router.get('/{league_id}/messages', response_model=MessagesPageResponse)
async def get_messages(
    league_id: uuid.UUID,
    cursor:    str | None   = Query(None, description='Opaque pagination cursor from a previous page'),
    limit:     int          = Query(25, ge=1, le=100),
    coach:     Coach        = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    await _require_league_team(db, league_id, coach)

    query = (
        select(LeagueMessage)
        .where(LeagueMessage.league_id == league_id, LeagueMessage.deleted_at.is_(None))
        .order_by(LeagueMessage.created_at.desc(), LeagueMessage.id.desc())
    )
    if cursor is not None:
        try:
            c_ts, c_id = _decode_cursor(cursor)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail='Invalid cursor')
        query = query.where(
            or_(
                LeagueMessage.created_at < c_ts,
                and_(LeagueMessage.created_at == c_ts, LeagueMessage.id < c_id),
            )
        )

    result = await db.execute(query.limit(limit + 1))
    rows = result.scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]

    return MessagesPageResponse(
        items=[
            MessageItem(
                id=m.id,
                team_id=m.team_id,
                team_name=m.team_name,
                coach_name=m.coach_name,
                body=m.body,
                created_at=m.created_at.isoformat(),
                is_mine=(m.coach_id == coach.id),
            )
            for m in page
        ],
        next_cursor=_encode_cursor(page[-1]) if has_more and page else None,
    )


@router.post('/{league_id}/messages', response_model=MessageItem, status_code=201)
async def post_message(
    league_id: uuid.UUID,
    body:      PostMessageRequest,
    coach:     Coach        = Depends(get_current_coach),
    db:        AsyncSession = Depends(get_db),
):
    team = await _require_league_team(db, league_id, coach)

    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Message cannot be empty')

    # Set id + created_at explicitly so we never read back an expired row post-commit.
    now = datetime.now(timezone.utc)
    msg = LeagueMessage(
        id=uuid.uuid4(),
        league_id=league_id,
        team_id=team.id,
        coach_id=coach.id,
        team_name=team.name,
        coach_name=coach.display_name,
        body=text,
        created_at=now,
    )
    db.add(msg)
    await db.commit()

    return MessageItem(
        id=msg.id,
        team_id=team.id,
        team_name=team.name,
        coach_name=coach.display_name,
        body=text,
        created_at=now.isoformat(),
        is_mine=True,
    )


@router.delete('/{league_id}/messages/{message_id}', status_code=204)
async def delete_message(
    league_id:  uuid.UUID,
    message_id: uuid.UUID,
    coach:      Coach        = Depends(get_current_coach),
    db:         AsyncSession = Depends(get_db),
):
    msg = await db.get(LeagueMessage, message_id)
    if not msg or msg.league_id != league_id or msg.deleted_at is not None:
        raise HTTPException(status_code=404, detail='Message not found')
    if msg.coach_id != coach.id:
        raise HTTPException(status_code=403, detail='You can only delete your own messages')
    msg.deleted_at = datetime.now(timezone.utc)
    await db.commit()
