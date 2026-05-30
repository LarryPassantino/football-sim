import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from sim.player_gen import POSITION_STATS, assign_label
from sqlalchemy import func
from ..models import Coach, Game, GameStatus, League, LeagueStatus, Player, PlayerGameStats, Season, SeasonStatus, Team
from ..schemas import (
    ActivateRequest, AvailableLeaguesResponse, DefenseLeader, GameDetailResponse,
    GameMatchupResponse, GamePlanRequest, GameResponse, GroupComposite, LeagueAvailableItem,
    LeagueCreateRequest, LeagueDetailResponse, LeagueLeadersResponse, LeagueResponse, PassingLeader,
    PlayerRosterItem, PlayerScoutItem, PlayerStatLine, PlayerStatsResponse, ReceivingLeader,
    ReleaseRequest, ReleaseResponse, RushingLeader, SignFARequest, StandingRow, StandingsResponse,
    TeamMatchupSide, TeamPickerItem, TeamRenameRequest, TeamResponse, TradeRequest, TradeResponse,
)
from ..services.league_service import create_league, OFFSEASON_DAYS

router = APIRouter(prefix='/leagues', tags=['leagues'])


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

    offseason_days_remaining = None
    if league.status == LeagueStatus.offseason and latest_season and latest_season.completed_at:
        elapsed = (datetime.now(timezone.utc) - latest_season.completed_at).days
        offseason_days_remaining = max(0, OFFSEASON_DAYS - elapsed)

    season_status = None
    if league.status == LeagueStatus.offseason:
        season_status = 'offseason'
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
        .where(Player.league_id == league_id, Player.team_id.is_(None))
        .order_by(Player.position)
    )
    items = _to_scout_items(result.scalars().all())
    items.sort(key=lambda x: (x.position, _LABEL_ORDER.get(x.composite_label, 99), x.name))
    return items


_POSITION_MAX_ACTIVE = {
    'QB': 2, 'WR': 4, 'TE': 2, 'RB': 2, 'OL': 6,
    'DT': 3, 'DE': 3, 'LB': 4, 'CB': 3, 'S': 3,
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
    if not player or player.league_id != league_id or player.team_id is not None:
        raise HTTPException(status_code=404, detail='Player not available')

    result = await db.execute(
        select(func.count()).where(
            Player.team_id  == team_id,
            Player.on_ir    == False,  # noqa: E712
            Player.position == player.position,
        )
    )
    active_at_pos = result.scalar()
    if active_at_pos >= _POSITION_MAX_ACTIVE.get(player.position, 0):
        raise HTTPException(status_code=409, detail=f'No open {player.position} slot on active roster')

    player.team_id = team_id
    player.on_ir   = False
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

    drop     = await db.get(Player, body.drop_player_id)
    activate = await db.get(Player, body.activate_player_id)

    if not drop or drop.team_id != team_id or drop.on_ir:
        raise HTTPException(status_code=400, detail='Drop player must be active on your roster')
    if not activate or activate.team_id != team_id or not activate.on_ir:
        raise HTTPException(status_code=400, detail='Activate player must be on IR on your roster')
    if activate.injury_games_remaining > 0:
        raise HTTPException(status_code=400, detail='Player not yet recovered')
    if drop.position != activate.position:
        raise HTTPException(status_code=400, detail=f'Must drop a {activate.position} to activate a {activate.position}')

    drop.team_id    = None
    drop.on_ir      = False
    activate.on_ir  = False
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
    await db.commit()
    return TradeResponse(accepted=True, reason='Trade accepted')


_LABEL_ORDER  = {'Elite': 0, 'Above Avg': 1, 'Average': 2, 'Below Avg': 3, 'Weak': 4}
_FITNESS_STATS = frozenset({'AGILITY', 'STAMINA', 'STRENGTH'})


def _reorder_stats(stat_names: list[str]) -> list[str]:
    if len(stat_names) <= 1:
        return list(stat_names)
    skill = stat_names[0]
    rest  = stat_names[1:]
    return [skill] + sorted(s for s in rest if s not in _FITNESS_STATS) \
                   + sorted(s for s in rest if s in _FITNESS_STATS)


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
        select(Season).where(Season.league_id == league_id)
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

    result = await db.execute(select(Season).where(Season.league_id == league_id))
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
    result = await db.execute(select(Season).where(Season.league_id == league_id))
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

    result = await db.execute(select(Season).where(Season.league_id == league_id))
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


@router.get('/{league_id}/leaders', response_model=LeagueLeadersResponse)
async def get_league_leaders(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Season).where(Season.league_id == league_id))
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
        .where(Game.season_id == season.id)
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
    defense.sort(key=lambda x: x.tackles, reverse=True)

    return LeagueLeadersResponse(
        passing=passing[:10],
        rushing=rushing[:10],
        receiving=receiving[:10],
        defense=defense[:10],
    )
