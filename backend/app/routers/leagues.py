import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from sim.player_gen import POSITION_STATS, assign_label
from ..models import Coach, Game, GameStatus, League, Player, PlayerGameStats, Season, Team
from ..schemas import (
    AvailableLeaguesResponse, GameDetailResponse, GameResponse, LeagueAvailableItem,
    LeagueCreateRequest, LeagueDetailResponse, LeagueResponse, PlayerRosterItem,
    PlayerScoutItem, PlayerStatLine, StandingRow, StandingsResponse, TeamPickerItem,
    TeamResponse,
)
from ..services.league_service import create_league

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
    result = await db.execute(select(Season).where(Season.league_id == league_id))
    season = result.scalar_one_or_none()
    return LeagueDetailResponse(
        id=league.id,
        name=league.name,
        status=league.status,
        current_week=season.current_week if season else None,
        season_status=season.status.value if season else None,
        created_at=league.created_at,
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
        items.append(PlayerRosterItem(
            id=p.id,
            name=p.name,
            position=p.position,
            age=p.age,
            composite=p.composite,
            named_stats={name: val for name, val in zip(stat_names, p.stats)},
            injury_games_remaining=p.injury_games_remaining,
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
        .order_by(Player.position, Player.composite.desc())
    )
    return _to_scout_items(result.scalars().all())


def _to_scout_items(players) -> list[PlayerScoutItem]:
    items = []
    for p in players:
        stat_names = POSITION_STATS.get(p.position, [])
        items.append(PlayerScoutItem(
            id=p.id,
            name=p.name,
            position=p.position,
            age=p.age,
            composite_label=assign_label(p.composite),
            named_stat_labels={name: assign_label(val) for name, val in zip(stat_names, p.stats)},
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
