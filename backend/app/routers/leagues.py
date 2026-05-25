import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from ..models import Coach, Game, GameStatus, League, Player, PlayerGameStats, Season, Team
from ..schemas import (
    GameDetailResponse, GameResponse, LeagueCreateRequest,
    LeagueResponse, PlayerStatLine, StandingRow, StandingsResponse, TeamResponse,
)
from ..services.league_service import create_league

router = APIRouter(prefix='/leagues', tags=['leagues'])


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


@router.get('/{league_id}', response_model=LeagueResponse)
async def get_league(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    league = await db.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail='League not found')
    return league


@router.get('/{league_id}/teams', response_model=list[TeamResponse])
async def get_teams(league_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.league_id == league_id))
    return result.scalars().all()


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
        else:
            away['wins'] += 1
            home['losses'] += 1

    standing_list = [
        StandingRow(**r, point_differential=r['points_for'] - r['points_against'])
        for r in rows.values()
    ]
    standing_list.sort(key=lambda r: (r.conference, r.division, -r.wins, -r.point_differential))

    return StandingsResponse(standings=standing_list)
