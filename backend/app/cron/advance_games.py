"""
advance_games.py — Railway cron entry point.

Railway command: python -m app.cron.advance_games
Working directory: backend/

Finds all active leagues and advances each by one step:
  - regular / playoffs  → simulate next week of games
  - offseason           → after OFFSEASON_DAYS, run the full draft → preseason
  - preseason           → after PRESEASON_DAYS, start regular season
"""

import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from ..database import SessionLocal
from ..models import League, LeagueStatus, Season
from ..services.league_service import (
    OFFSEASON_DAYS,
    PRESEASON_DAYS,
    advance_week,
    end_preseason,
    run_full_draft,
)
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        # ── Regular season and playoff advancement ──────────────────────────
        result = await db.execute(
            select(League).where(
                League.status.in_([LeagueStatus.regular, LeagueStatus.playoffs])
            )
        )
        for league in result.scalars().all():
            summary = await advance_week(db, league.id)
            print(f"[{league.name}] {summary}")

        # ── Offseason → run draft after window expires ──────────────────────
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
                    await run_full_draft(db, league.id)
                    print(f"[{league.name}] Draft complete — preseason started")

        # ── Preseason → start regular season after window expires ───────────
        result = await db.execute(
            select(League).where(League.status == LeagueStatus.preseason)
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
                # Preseason window starts after the offseason window ends
                if elapsed >= OFFSEASON_DAYS + PRESEASON_DAYS:
                    await end_preseason(db, league.id)
                    print(f"[{league.name}] Season {last.season_number + 1} started")


if __name__ == '__main__':
    asyncio.run(main())
