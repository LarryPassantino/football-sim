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
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'))

from ..database import SessionLocal
from ..models import League, LeagueStatus
from ..services.league_service import advance_week
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        result  = await db.execute(select(League).where(League.status == LeagueStatus.regular))
        leagues = result.scalars().all()

        for league in leagues:
            summary = await advance_week(db, league.id)
            print(f"[{league.name}] {summary}")

        print(f"Processed {len(leagues)} league(s)")


if __name__ == '__main__':
    asyncio.run(main())
