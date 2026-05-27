from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_coach, get_db
from ..models import Coach, League, Team
from ..schemas import CoachTeamItem

router = APIRouter(prefix='/coaches', tags=['coaches'])


@router.get('/me/teams', response_model=list[CoachTeamItem])
async def get_my_teams(
    coach: Coach = Depends(get_current_coach),
    db:    AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Team, League)
        .join(League, Team.league_id == League.id)
        .where(Team.coach_id == coach.id)
    )
    return [
        CoachTeamItem(
            team_id=team.id,
            team_name=team.name,
            league_id=league.id,
            league_name=league.name,
            conference=team.conference,
            division=team.division,
        )
        for team, league in result.all()
    ]
