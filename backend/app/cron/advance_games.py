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
    generate_annual_draft_class,
    repair_season_schedule,
    run_full_draft,
)
from sqlalchemy import select


async def main():
    async with SessionLocal() as db:
        # ── ONE-TIME: repair dropped games from _assign_weeks bug ───────────
        result = await db.execute(
            select(League).where(League.status == LeagueStatus.regular)
        )
        for league in result.scalars().all():
            summary = await repair_season_schedule(db, league.id)
            print(f"[{league.name}] schedule repair: {summary}")
        await db.commit()

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
            if not last or not last.completed_at:
                print(f"[{league.name}] Offseason: no completed season found — skipping")
                continue

            # Ensure draft class was generated (guards against a prior crash in end_season)
            draft_ready = (
                last.draft_state and
                last.draft_state.get('order') and
                last.draft_state.get('total_picks')
            )
            if not draft_ready:
                print(f"[{league.name}] Offseason: draft class missing — generating now")
                await generate_annual_draft_class(db, league.id)
                print(f"[{league.name}] Offseason: draft class generated")
                continue  # let next cron run handle elapsed check cleanly

            elapsed = (datetime.now(timezone.utc) - last.completed_at).days
            print(f"[{league.name}] Offseason: {elapsed}/{OFFSEASON_DAYS} days elapsed")
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
