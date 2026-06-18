"""
repair_schedule.py — one-time fix for seasons with dropped games from _assign_weeks bug.

Railway command: python -m app.cron.repair_schedule
Working directory: backend/
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from ..database import SessionLocal
from ..models import League, LeagueStatus
from ..services.league_service import repair_season_schedule
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        result = await db.execute(
            select(League).where(League.status == LeagueStatus.regular)
        )
        for league in result.scalars().all():
            summary = await repair_season_schedule(db, league.id)
            print(f"[{league.name}] {summary}")
        await db.commit()


if __name__ == '__main__':
    asyncio.run(main())
