"""
advance_games.py — Railway cron entry point.

Railway command: python -m app.cron.advance_games
Working directory: backend/

Finds all leagues in 'regular' status and advances each by one week.
Set the Railway cron to whatever interval you want (3 min for testing,
daily for production — one week of games per tick).
"""

import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from ..database import SessionLocal
from ..models import League, LeagueStatus, Season
from ..services.league_service import OFFSEASON_DAYS, advance_week, start_new_season
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        # Advance regular season and playoff leagues
        result = await db.execute(
            select(League).where(
                League.status.in_([LeagueStatus.regular, LeagueStatus.playoffs])
            )
        )
        for league in result.scalars().all():
            summary = await advance_week(db, league.id)
            print(f"[{league.name}] {summary}")

        # Start new season for leagues past their offseason window
        result = await db.execute(
            select(League).where(League.status == LeagueStatus.offseason)
        )
        for league in result.scalars().all():
            result2 = await db.execute(
                select(Season)
                .where(Season.league_id == league.id)
                .order_by(Season.season_number.desc())
                .limit(1)
            )
            last = result2.scalar_one_or_none()
            if last and last.completed_at:
                elapsed = (datetime.now(timezone.utc) - last.completed_at).days
                if elapsed >= OFFSEASON_DAYS:
                    await start_new_season(db, league.id)
                    print(f"[{league.name}] Season {last.season_number + 1} started")


if __name__ == '__main__':
    asyncio.run(main())
