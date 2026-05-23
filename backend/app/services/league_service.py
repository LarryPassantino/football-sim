"""
league_service.py — League creation and season advancement.

create_league: generates the full player pool, runs the CPU mega-draft,
  persists all teams/players, builds and stores the 17-week schedule.

advance_week: called by the cron job once per tick; plays all games in
  the current week and transitions season state when appropriate.
"""

import os
import sys
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sim.draft_sim import LEAGUE as LEAGUE_STRUCTURE, build_teams, run_draft
from sim.player_gen import generate_pool
from sim.season_sim import build_schedule

from ..models import (
    Game, GameStatus, League, LeagueStatus,
    Player, Season, SeasonStatus, Team,
)
from .sim_bridge import clear_all_injuries, play_game

REGULAR_SEASON_WEEKS = 17


# ============================================================
# WEEK ASSIGNMENT
# Greedy: assign each game to the earliest week where neither
# team already has a game scheduled.
# ============================================================

def _assign_weeks(schedule: list[tuple], n_weeks: int = REGULAR_SEASON_WEEKS) -> dict[int, list[tuple]]:
    weeks: dict[int, list] = {w: [] for w in range(1, n_weeks + 1)}
    teams_per_week: dict[int, set] = {w: set() for w in range(1, n_weeks + 1)}

    for h_idx, a_idx in schedule:
        for w in range(1, n_weeks + 1):
            if h_idx not in teams_per_week[w] and a_idx not in teams_per_week[w]:
                weeks[w].append((h_idx, a_idx))
                teams_per_week[w].add(h_idx)
                teams_per_week[w].add(a_idx)
                break

    return weeks


# ============================================================
# LEAGUE CREATION
# ============================================================

async def create_league(db: AsyncSession, name: str) -> League:
    league = League(name=name)
    db.add(league)
    await db.flush()

    # Run the full sim pipeline (CPU-only draft)
    pool      = generate_pool()
    sim_teams = build_teams()
    sim_teams, fa_pool = run_draft(sim_teams, pool, show_rounds=0)

    # Persist teams and their rosters
    team_idx_to_db: dict[int, Team] = {}
    for idx, sim_team in enumerate(sim_teams):
        team = Team(
            league_id=league.id,
            name=sim_team['name'],
            conference=sim_team['conference'],
            division=sim_team['division'],
            is_cpu=True,
        )
        db.add(team)
        await db.flush()
        team_idx_to_db[idx] = team

        for pos, players in sim_team['roster'].items():
            for p in players:
                db.add(Player(
                    league_id=league.id,
                    team_id=team.id,
                    name=p['name'],
                    position=pos,
                    age=p['age'],
                    stats=p['stats'],
                    composite=p['composite'],
                    potential=p['potential'],
                ))

    # Persist FA pool (team_id=None)
    for pos, players in fa_pool.items():
        for p in players:
            db.add(Player(
                league_id=league.id,
                team_id=None,
                name=p['name'],
                position=pos,
                age=p['age'],
                stats=p['stats'],
                composite=p['composite'],
                potential=p['potential'],
            ))

    # Create season and schedule
    season = Season(league_id=league.id, season_number=1, current_week=1)
    db.add(season)
    await db.flush()

    schedule = build_schedule(sim_teams)
    weeks    = _assign_weeks(schedule)

    for week_num, games in weeks.items():
        for h_idx, a_idx in games:
            db.add(Game(
                season_id=season.id,
                week=week_num,
                home_team_id=team_idx_to_db[h_idx].id,
                away_team_id=team_idx_to_db[a_idx].id,
            ))

    league.status = LeagueStatus.regular
    await db.commit()
    return league


# ============================================================
# WEEK ADVANCEMENT (called by cron)
# ============================================================

async def advance_week(db: AsyncSession, league_id: uuid.UUID) -> dict:
    """
    Play all games in the current week for this league.
    Returns a summary dict for logging.
    """
    result = await db.execute(
        select(Season).where(
            Season.league_id == league_id,
            Season.status == SeasonStatus.regular,
        )
    )
    season = result.scalar_one_or_none()
    if not season:
        return {'skipped': True, 'reason': 'no active regular season'}

    result = await db.execute(
        select(Game)
        .where(Game.season_id == season.id, Game.week == season.current_week)
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
    )
    games = result.scalars().all()

    games_remaining = REGULAR_SEASON_WEEKS - season.current_week + 1

    for game in games:
        if game.status == GameStatus.complete:
            continue
        await play_game(db, game, game.home_team, game.away_team, games_remaining)

    season.current_week += 1

    if season.current_week > REGULAR_SEASON_WEEKS:
        season.status = SeasonStatus.playoffs
        # TODO: build and run playoff bracket

    await db.commit()
    return {'week_played': season.current_week - 1, 'games': len(games)}


async def end_season(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Clear injuries and move league to offseason."""
    await clear_all_injuries(db, league_id)

    result = await db.execute(select(League).where(League.id == league_id))
    league = result.scalar_one()
    league.status = LeagueStatus.offseason

    result = await db.execute(
        select(Season).where(Season.league_id == league_id, Season.status != SeasonStatus.complete)
    )
    season = result.scalar_one_or_none()
    if season:
        season.status = SeasonStatus.complete

    await db.commit()
