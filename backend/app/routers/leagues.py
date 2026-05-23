import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from ..models import Coach, Game, League, Season, Team
from ..schemas import GameResponse, LeagueCreateRequest, LeagueResponse, TeamResponse
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
