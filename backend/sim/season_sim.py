"""
season_sim.py — Regular season + playoffs
Bridges draft_sim rosters into the football_sim game engine.
"""

import random
from collections import defaultdict

from .player_gen import generate_pool
from .draft_sim import build_teams, run_draft, LEAGUE
from .football_sim import simulate_game
from .injury_sim import (
    roll_pregame_injuries, tick_injuries,
    build_game_day_sim_team, season_injury_report, clear_season_injuries,
)




# ============================================================
# SCHEDULE GENERATOR
# 17 games: 6 division (×2) + 4 conf non-div (×1) + 7 cross-conf (×1)
# Total: 136 games, 8 per week, 17 weeks
# ============================================================

def build_schedule(teams):
    """Returns list of (home_idx, away_idx) for all 136 regular season games."""
    by_div  = defaultdict(list)
    by_conf = defaultdict(list)
    for i, t in enumerate(teams):
        by_div[(t['conference'], t['division'])].append(i)
        by_conf[t['conference']].append(i)

    games = []

    # Division home-and-home (3 pairs × 2 = 6 games per team)
    for members in by_div.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                games.append((a, b))
                games.append((b, a))

    # Conference non-division (4 games per team, 1 each)
    for conf_members in by_conf.values():
        divs = sorted({teams[i]['division'] for i in conf_members})
        div1 = [i for i in conf_members if teams[i]['division'] == divs[0]]
        div2 = [i for i in conf_members if teams[i]['division'] == divs[1]]
        for a in div1:
            for b in div2:
                h, aw = (a, b) if random.random() < 0.5 else (b, a)
                games.append((h, aw))

    # Cross-conference (7 of 8 opponents, skip bijection for balance)
    games.extend(_cross_conf_games(
        by_conf['Conference A'],
        by_conf['Conference B'],
    ))

    random.shuffle(games)
    return games


def _cross_conf_games(conf_a, conf_b):
    """
    Each team plays 7 of 8 cross-conf opponents (one skip per team).
    Skip bijection: each conf B team is skipped by exactly 1 conf A team,
    so the schedule is perfectly balanced across both conferences.
    """
    games   = []
    b_order = list(conf_b)
    random.shuffle(b_order)
    for i, a in enumerate(conf_a):
        skip = b_order[i]
        for b in conf_b:
            if b == skip:
                continue
            h, aw = (a, b) if random.random() < 0.5 else (b, a)
            games.append((h, aw))
    return games


# ============================================================
# STANDINGS
# ============================================================

def make_standings(draft_teams):
    return {
        t['name']: {
            'team': t,
            'W': 0, 'L': 0, 'T': 0,
            'PF': 0, 'PA': 0,
            'results': [],      # [(opp_name, pf, pa), ...]
        }
        for t in draft_teams
    }


def record_result(standings, home_team, away_team, sh, sa):
    h = standings[home_team['name']]
    a = standings[away_team['name']]
    h['PF'] += sh;  h['PA'] += sa
    a['PF'] += sa;  a['PA'] += sh
    h['results'].append((away_team['name'], sh, sa))
    a['results'].append((home_team['name'], sa, sh))
    if sh > sa:
        h['W'] += 1;  a['L'] += 1
    elif sa > sh:
        a['W'] += 1;  h['L'] += 1
    else:
        h['T'] += 1;  a['T'] += 1


def win_pct(row):
    g = row['W'] + row['L'] + row['T']
    return (row['W'] + 0.5 * row['T']) / g if g else 0.0


def _h2h_pct(row_a, row_b):
    opp = row_b['team']['name']
    w = l = t = 0
    for name, pf, pa in row_a['results']:
        if name == opp:
            if   pf > pa: w += 1
            elif pa > pf: l += 1
            else:         t += 1
    g = w + l + t
    return (w + 0.5 * t) / g if g else 0.5


def sort_group(rows):
    """Win% → h2h (2-way ties only) → point diff → coin flip."""
    rows = sorted(rows, key=lambda r: (win_pct(r), r['PF'] - r['PA']), reverse=True)
    i = 0
    while i < len(rows) - 1:
        if abs(win_pct(rows[i]) - win_pct(rows[i + 1])) < 1e-9:
            j = i + 1
            while j < len(rows) and abs(win_pct(rows[j]) - win_pct(rows[i])) < 1e-9:
                j += 1
            if j - i == 2:
                if _h2h_pct(rows[i], rows[i + 1]) < _h2h_pct(rows[i + 1], rows[i]):
                    rows[i], rows[i + 1] = rows[i + 1], rows[i]
            i = j
        else:
            i += 1
    return rows


# ============================================================
# SEASON RUNNER
# ============================================================

REGULAR_SEASON_GAMES = 17

def run_season(draft_teams, schedule):
    """
    Simulate all 136 regular season games with per-game injury resolution.
    Returns (standings dict, {team_name: draft_team}) for playoff use.
    """
    standings       = make_standings(draft_teams)
    team_game_count = [0] * len(draft_teams)

    for home_idx, away_idx in schedule:
        h = draft_teams[home_idx]
        a = draft_teams[away_idx]

        h_remaining = REGULAR_SEASON_GAMES - team_game_count[home_idx]
        a_remaining = REGULAR_SEASON_GAMES - team_game_count[away_idx]

        roll_pregame_injuries(h, h_remaining)
        roll_pregame_injuries(a, a_remaining)

        sh, sa, _, _ = simulate_game(
            build_game_day_sim_team(h),
            build_game_day_sim_team(a),
        )
        record_result(standings, h, a, sh, sa)

        tick_injuries(h)
        tick_injuries(a)

        team_game_count[home_idx] += 1
        team_game_count[away_idx] += 1

    name_to_draft = {t['name']: t for t in draft_teams}
    return standings, name_to_draft


# ============================================================
# DISPLAY
# ============================================================

def show_standings(standings):
    print(f"\n{'='*70}")
    print(f"  Regular Season Standings")
    print(f"{'='*70}")
    for conf, divisions in LEAGUE.items():
        print(f"\n  {conf}")
        for div, div_names in divisions.items():
            rows = sort_group([standings[n] for n in div_names])
            print(f"\n    {div}")
            print(f"    {'Team':<24}  {'W':>3} {'L':>3} {'T':>3}  {'PCT':>5}  {'PF':>5}  {'PA':>5}  {'DIFF':>5}")
            print(f"    {'-'*58}")
            for row in rows:
                pct  = win_pct(row)
                diff = row['PF'] - row['PA']
                sign = '+' if diff >= 0 else ''
                print(f"    {row['team']['name']:<24}  {row['W']:>3} {row['L']:>3} {row['T']:>3}  "
                      f"{pct:>5.3f}  {row['PF']:>5}  {row['PA']:>5}  {sign}{diff:>4}")


def show_league_leaders(standings):
    print(f"\n{'='*65}")
    print(f"  Overall League Standings")
    print(f"{'='*65}")
    rows = sorted(standings.values(), key=lambda r: (win_pct(r), r['PF'] - r['PA']), reverse=True)
    print(f"  {'':>3}  {'Team':<26} {'W':>3} {'L':>3} {'T':>3}  {'PCT':>5}  {'PF':>5}  {'PA':>5}")
    print(f"  {'-'*60}")
    for rank, row in enumerate(rows, 1):
        print(f"  {rank:>2}.  {row['team']['name']:<26} {row['W']:>3} {row['L']:>3} {row['T']:>3}  "
              f"{win_pct(row):>5.3f}  {row['PF']:>5}  {row['PA']:>5}")


# ============================================================
# PLAYOFFS
# 4 teams per conference: 2 division winners + 2 wildcards
# Bracket: #1 vs #4, #2 vs #3 → conf championship → championship
# ============================================================

def get_seeds(standings):
    """Returns {conf: [row_1, row_2, row_3, row_4]}."""
    seeds = {}
    for conf, divisions in LEAGUE.items():
        div_winners = []
        wild_pool   = []
        for div, div_names in divisions.items():
            rows = sort_group([standings[n] for n in div_names])
            div_winners.append(rows[0])
            wild_pool.extend(rows[1:])
        seeds[conf] = sort_group(div_winners) + sort_group(wild_pool)[:2]
    return seeds


def _playoff_game(name_to_draft, row_a, row_b):
    """Simulate one playoff game (re-roll on tie = OT). Returns (winner, loser, sa, sb)."""
    dt_a = name_to_draft[row_a['team']['name']]
    dt_b = name_to_draft[row_b['team']['name']]

    roll_pregame_injuries(dt_a, 1)
    roll_pregame_injuries(dt_b, 1)

    sa = sb = 0
    while sa == sb:
        sa, sb, _, _ = simulate_game(
            build_game_day_sim_team(dt_a),
            build_game_day_sim_team(dt_b),
        )

    tick_injuries(dt_a)
    tick_injuries(dt_b)

    if sa > sb:
        return row_a, row_b, sa, sb
    return row_b, row_a, sb, sa


def run_playoffs(standings, name_to_draft):
    seeds = get_seeds(standings)

    print(f"\n{'='*65}")
    print(f"  PLAYOFFS")
    print(f"{'='*65}")

    conf_champs = []
    for conf in ['Conference A', 'Conference B']:
        s = seeds[conf]
        print(f"\n  {conf} Semifinals")
        r1_winners = []
        for top, bot in [(s[0], s[3]), (s[1], s[2])]:
            t_seed = s.index(top) + 1
            b_seed = s.index(bot) + 1
            winner, loser, sa, sb = _playoff_game(name_to_draft, top, bot)
            t_score = sa if winner is top else sb
            b_score = sb if winner is top else sa
            print(f"    #{t_seed} {top['team']['name']:<24} {t_score:>2}  "
                  f"#{b_seed} {bot['team']['name']:<24} {b_score:>2}  "
                  f"  -> {winner['team']['name']}")
            r1_winners.append(winner)

        print(f"\n  {conf} Championship")
        winner, loser, sa, sb = _playoff_game(name_to_draft, r1_winners[0], r1_winners[1])
        w0 = sa if winner is r1_winners[0] else sb
        w1 = sb if winner is r1_winners[0] else sa
        print(f"    {r1_winners[0]['team']['name']:<26} {w0:>2}")
        print(f"    {r1_winners[1]['team']['name']:<26} {w1:>2}")
        print(f"    -> {winner['team']['name']}")
        conf_champs.append(winner)

    print(f"\n{'='*65}")
    print(f"  CHAMPIONSHIP GAME")
    print(f"{'='*65}")
    champion, runner_up, sa, sb = _playoff_game(name_to_draft, conf_champs[0], conf_champs[1])
    c0 = sa if champion is conf_champs[0] else sb
    c1 = sb if champion is conf_champs[0] else sa
    print(f"  {conf_champs[0]['team']['name']:<28} {c0:>2}")
    print(f"  {conf_champs[1]['team']['name']:<28} {c1:>2}")
    print(f"\n  CHAMPION: {champion['team']['name'].upper()}")
    return champion


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    random.seed(42)

    print("Generating player pool and running mega draft...")
    pool  = generate_pool()
    teams = build_teams()
    teams, fa_pool = run_draft(teams, pool, show_rounds=0)

    print(f"\nBuilding schedule (17 games x {len(teams)} teams = 136 games)...")
    schedule = build_schedule(teams)
    print(f"  Schedule: {len(schedule)} games")

    # Verify game counts per team
    counts = defaultdict(int)
    for h, a in schedule:
        counts[h] += 1
        counts[a] += 1
    if all(c == 17 for c in counts.values()):
        print(f"  All {len(teams)} teams have exactly 17 games")
    else:
        for idx, c in counts.items():
            if c != 17:
                print(f"  WARNING: {teams[idx]['name']} has {c} games (expected 17)")

    print("\nSimulating regular season...")
    standings, name_to_draft = run_season(teams, schedule)

    show_standings(standings)
    show_league_leaders(standings)
    season_injury_report(teams)

    run_playoffs(standings, name_to_draft)
    clear_season_injuries(teams)
