"""
sim_bridge.py — Translates between DB models and the sim engine's dict format.

The sim engine works entirely with Python dicts. This module loads team data
from the DB into that format, runs sim operations, and writes results back.
Players get a _db_id key (not used by the sim) so we can target DB updates.
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# Make the sim package importable from the football project root
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sim.football_sim import ROSTER_SLOTS as SIM_SLOTS, simulate_game
from sim.injury_sim import (
    build_game_day_sim_team, roll_pregame_injuries, tick_injuries,
)

from ..models import Game, GameStatus, Player


async def load_team_as_sim_dict(db: AsyncSession, team) -> dict:
    """
    Load a Team ORM object + its players into the dict format the sim engine expects:
    { 'name': ..., 'conference': ..., 'division': ..., 'roster': {pos: [player_dicts]} }

    Players are sorted by composite DESC within each position (starter-first ordering
    that the sim engine relies on).
    """
    result  = await db.execute(select(Player).where(Player.team_id == team.id))
    players = result.scalars().all()

    roster = defaultdict(list)
    for p in players:
        roster[p.position].append({
            'name':                   p.name,
            'position':               p.position,
            'age':                    p.age,
            'stats':                  p.stats,
            'composite':              p.composite,
            'potential':              p.potential,
            'injury_games_remaining': p.injury_games_remaining,
            '_db_id':                 str(p.id),
        })

    for pos in roster:
        roster[pos].sort(key=lambda p: p['composite'], reverse=True)

    return {
        'name':       team.name,
        'conference': team.conference,
        'division':   team.division,
        'roster':     dict(roster),
    }


async def write_back_injuries(db: AsyncSession, sim_team: dict) -> None:
    """Persist injury_games_remaining changes from sim dicts back to DB."""
    for players in sim_team['roster'].values():
        for p in players:
            if '_db_id' not in p:
                continue
            await db.execute(
                update(Player)
                .where(Player.id == p['_db_id'])
                .values(injury_games_remaining=p['injury_games_remaining'])
            )


async def clear_all_injuries(db: AsyncSession, league_id) -> None:
    """Reset all injury timers for a league at season end."""
    await db.execute(
        update(Player)
        .where(Player.league_id == league_id)
        .values(injury_games_remaining=0)
    )


async def play_game(db: AsyncSession, game: Game, home_team, away_team, games_remaining: int) -> None:
    """
    Simulate a single game: roll injuries, build game-day rosters, run sim,
    write scores and injury state back to DB.
    """
    home_sim = await load_team_as_sim_dict(db, home_team)
    away_sim = await load_team_as_sim_dict(db, away_team)

    roll_pregame_injuries(home_sim, games_remaining)
    roll_pregame_injuries(away_sim, games_remaining)

    home_score, away_score, _, _ = simulate_game(
        build_game_day_sim_team(home_sim),
        build_game_day_sim_team(away_sim),
    )

    tick_injuries(home_sim)
    tick_injuries(away_sim)

    await write_back_injuries(db, home_sim)
    await write_back_injuries(db, away_sim)

    game.home_score = home_score
    game.away_score = away_score
    game.status     = GameStatus.complete
    game.played_at  = datetime.now(timezone.utc)
