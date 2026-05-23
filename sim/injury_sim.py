"""
injury_sim.py — Pre-game injury resolution and season-long tracking.

Injuries are rolled per healthy starter before each game. Duration is determined
upfront at injury time. Fitness score (avg STR/AGI/STA) affects both occurrence
rate and severity tier.

Season-ending injuries set injury_games_remaining = games_remaining_at_injury_time,
which ticks down naturally to 0 by season end — no special sentinel needed.
"""

import random
from .player_gen import POSITION_STATS
from .football_sim import ROSTER_SLOTS as SIM_SLOTS, make_team_from_roster

# Stats that feed the fitness score
_FITNESS_STATS = {'STRENGTH', 'AGILITY', 'STAMINA'}

FITNESS_BASELINE      = 70.0
BASE_INJURY_RATE      = 0.04   # per starter per game at avg fitness
RATE_SCALE            = 0.020  # rate shifts 2% per fitness point from baseline
TIER_SHIFT_SCALE      = 0.010  # tier weights shift 1% per fitness point from baseline
MAX_NEW_INJURIES_PER_GAME = 2  # cap on new injury rolls per team per game

# Tier weights at avg fitness (70); fitness shifts mild ↑ and season_ending ↓
_MILD_BASE        = 0.65
_SEASON_END_BASE  = 0.07
# moderate gets the remainder (~0.28)


# ============================================================
# FITNESS & RATE
# ============================================================

def fitness_score(player):
    """Average of STR/AGI/STA stats available for this position. K/P default to 70."""
    stat_names = POSITION_STATS[player['position']]
    vals = [v for s, v in zip(stat_names, player['stats']) if s in _FITNESS_STATS]
    return sum(vals) / len(vals) if vals else FITNESS_BASELINE


def _injury_rate(player):
    fit  = fitness_score(player)
    rate = BASE_INJURY_RATE * (1.0 - (fit - FITNESS_BASELINE) * RATE_SCALE)
    return max(0.005, min(0.15, rate))


# ============================================================
# DURATION ROLL
# ============================================================

def _roll_duration(fitness, games_remaining):
    """
    Roll injury duration (in games). Fitness biases tier selection.
    Mild: 1 game. Moderate: 2–4. Season-ending: games_remaining.
    """
    delta      = (fitness - FITNESS_BASELINE) * TIER_SHIFT_SCALE
    mild_w     = max(0.10, _MILD_BASE       + delta)
    season_w   = max(0.01, _SEASON_END_BASE - delta * 0.5)
    moderate_w = max(0.05, 1.0 - mild_w - season_w)

    roll = random.random() * (mild_w + moderate_w + season_w)
    if roll < mild_w:
        return 1
    if roll < mild_w + moderate_w:
        return random.randint(2, 4)
    return games_remaining


# ============================================================
# PER-GAME INJURY RESOLUTION
# ============================================================

def roll_pregame_injuries(draft_team, games_remaining):
    """
    Roll for new injuries on healthy starters before a game.
    Pre-existing injuries don't block new rolls; cap limits new injuries to
    MAX_NEW_INJURIES_PER_GAME per team per game. Modifies player dicts in place.
    """
    roster      = draft_team['roster']
    new_injuries = 0

    for pos, slots in SIM_SLOTS.items():
        for player in roster[pos][:slots['starters']]:
            if new_injuries >= MAX_NEW_INJURIES_PER_GAME:
                return
            if player.get('injury_games_remaining', 0) > 0:
                continue
            if random.random() < _injury_rate(player):
                fit = fitness_score(player)
                player['injury_games_remaining'] = _roll_duration(fit, games_remaining)
                new_injuries += 1


def tick_injuries(draft_team):
    """Advance injury recovery by one game for every player on the team."""
    for players in draft_team['roster'].values():
        for player in players:
            if player.get('injury_games_remaining', 0) > 0:
                player['injury_games_remaining'] -= 1


# ============================================================
# INJURY-AWARE ROSTER BRIDGE
# ============================================================

def build_game_day_sim_team(draft_team):
    """
    Build a sim-ready team dict for a single game, accounting for injuries.

    Injured starters are removed from the starters list; the backup is promoted
    into the starters list (one backup covers one injured starter slot). The
    backup slot becomes None once promoted. If all starters at a position are
    unavailable and there is no backup, the injured player is used as a fallback
    to prevent division-by-zero in group_composite.
    """
    roster    = draft_team['roster']
    sim_roster = {}

    for pos, slots in SIM_SLOTS.items():
        n_start    = slots['starters']
        has_backup = slots['backups'] > 0
        players    = roster[pos]

        healthy = [p for p in players[:n_start]
                   if p.get('injury_games_remaining', 0) == 0]
        backup  = players[n_start] if has_backup and len(players) > n_start else None
        injured = n_start - len(healthy)

        game_starters = list(healthy)
        game_backup   = backup

        if injured > 0 and backup is not None:
            game_starters.append(backup)
            game_backup = None

        # Absolute fallback: can't have an empty starters list (causes div/0)
        if not game_starters:
            game_starters = list(players[:n_start]) or ([backup] if backup else [])

        sim_roster[pos] = {'starters': game_starters, 'backup': game_backup}

    return make_team_from_roster(draft_team['name'], sim_roster)


# ============================================================
# REPORTING
# ============================================================

def clear_season_injuries(draft_teams):
    """Reset all injury timers at season end. Call after playoffs before next season."""
    for team in draft_teams:
        for players in team['roster'].values():
            for player in players:
                player['injury_games_remaining'] = 0


def season_injury_report(draft_teams):
    """Print each team's current injury list (players with games_remaining > 0)."""
    print(f"\n{'='*65}")
    print(f"  End-of-Season Injury Report")
    print(f"{'='*65}")
    any_injured = False
    for team in draft_teams:
        injured = [
            p for players in team['roster'].values()
            for p in players
            if p.get('injury_games_remaining', 0) > 0
        ]
        if injured:
            any_injured = True
            print(f"\n  {team['name']}")
            for p in injured:
                print(f"    {p['name']:<22} {p['position']:<4}  "
                      f"{p['injury_games_remaining']} game(s) remaining")
    if not any_injured:
        print("\n  No active injuries.")
