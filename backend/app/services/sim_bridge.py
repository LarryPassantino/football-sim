"""
sim_bridge.py — Translates between DB models and the sim engine's dict format.

The sim engine works entirely with Python dicts. This module loads team data
from the DB into that format, runs sim operations, and writes results back.
Players get a _db_id key (not used by the sim) so we can target DB updates.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sim.football_sim import ROSTER_SLOTS as SIM_SLOTS, apply_gameplan, simulate_game
from sim.injury_sim import (
    build_game_day_sim_team, roll_pregame_injuries, tick_injuries,
)
from sim.stats_gen import generate_game_stats

from ..models import Game, GameStatus, Player, PlayerGameStats


async def load_team_as_sim_dict(db: AsyncSession, team) -> dict:
    """
    Load a Team ORM object + its players into the dict format the sim engine expects:
    { 'name': ..., 'conference': ..., 'division': ..., 'roster': {pos: [player_dicts]} }

    Players are sorted by composite DESC within each position (starter-first ordering
    that the sim engine relies on).
    """
    result  = await db.execute(
        select(Player).where(Player.team_id == team.id, Player.on_ir == False)  # noqa: E712
    )
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
            igr    = p['injury_games_remaining']
            values = {'injury_games_remaining': igr}
            if igr > 0:
                values['on_ir'] = True
            await db.execute(
                update(Player)
                .where(Player.id == p['_db_id'])
                .values(**values)
            )


async def clear_all_injuries(db: AsyncSession, league_id) -> None:
    """Reset all injury timers for a league at season end."""
    await db.execute(
        update(Player)
        .where(Player.league_id == league_id)
        .values(injury_games_remaining=0, on_ir=False)
    )


_RUN_FACTORS = {'run_focus': 1.0, 'pass_focus': -1.0, 'balanced': 0.0}


async def play_game(
    db: AsyncSession,
    game: Game,
    home_team,
    away_team,
    games_remaining: int,
    home_off_plan: str = 'balanced',
    home_def_plan: str = 'balanced',
    away_off_plan: str = 'balanced',
    away_def_plan: str = 'balanced',
) -> None:
    """
    Simulate a single game: roll injuries, build game-day rosters, run sim,
    write scores, injury state, and per-player stats back to DB.
    """
    home_sim = await load_team_as_sim_dict(db, home_team)
    away_sim = await load_team_as_sim_dict(db, away_team)

    roll_pregame_injuries(home_sim, games_remaining)
    roll_pregame_injuries(away_sim, games_remaining)

    home_gd = apply_gameplan(build_game_day_sim_team(home_sim), home_off_plan, home_def_plan)
    away_gd = apply_gameplan(build_game_day_sim_team(away_sim), away_off_plan, away_def_plan)

    home_score, away_score, home_outcomes, away_outcomes = simulate_game(
        home_gd, away_gd, is_playoff=game.is_playoff,
    )

    tick_injuries(home_sim)
    tick_injuries(away_sim)

    await write_back_injuries(db, home_sim)
    await write_back_injuries(db, away_sim)

    # Generate and save per-player stats
    home_off, away_def = generate_game_stats(
        home_sim, away_sim, dict(home_outcomes),
        run_factor=_RUN_FACTORS.get(home_off_plan, 0.0),
    )
    away_off, home_def = generate_game_stats(
        away_sim, home_sim, dict(away_outcomes),
        run_factor=_RUN_FACTORS.get(away_off_plan, 0.0),
    )
    await _save_player_stats(db, game.id, home_team.id, home_off, home_def)
    await _save_player_stats(db, game.id, away_team.id, away_off, away_def)

    game.home_score = home_score
    game.away_score = away_score
    game.status     = GameStatus.complete
    game.played_at  = datetime.now(timezone.utc)


async def _save_player_stats(
    db: AsyncSession,
    game_id: uuid.UUID,
    team_id: uuid.UUID,
    off_stats: dict,
    def_stats: dict,
) -> None:
    """Merge offensive and defensive stat dicts for each player and insert rows."""
    all_ids = set(off_stats) | set(def_stats)
    for player_id_str in all_ids:
        merged = {}
        merged.update(off_stats.get(player_id_str, {}))
        for k, v in def_stats.get(player_id_str, {}).items():
            merged[k] = merged.get(k, 0) + v
        db.add(PlayerGameStats(
            game_id=game_id,
            player_id=uuid.UUID(player_id_str),
            team_id=team_id,
            **merged,
        ))
