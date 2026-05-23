import random
from collections import defaultdict
from .player_gen import generate_pool, assign_label, ROSTER_SLOTS

# ============================================================
# LEAGUE STRUCTURE
# 2 conferences, 2 divisions each, 4 teams per division = 16 teams
# ============================================================

LEAGUE = {
    'Conference A': {
        'Division 1': ['Northfield Wolves',   'Eastport Eagles',
                       'Riverdale Bears',      'Westbrook Falcons'],
        'Division 2': ['Lakeside Lions',       'Summit Tigers',
                       'Highland Hawks',       'Bayview Sharks'],
    },
    'Conference B': {
        'Division 1': ['Pinecrest Stallions',  'Clearwater Rams',
                       'Irongate Bulls',       'Crestwood Foxes'],
        'Division 2': ['Harborside Knights',   'Redstone Vipers',
                       'Sundale Cougars',      'Millfield Titans'],
    },
}

# ============================================================
# CPU DRAFT STRATEGY
# Urgency = base_priority × (slots_remaining / total_slots)
# Positions with high priority get drafted early even with fewer slots.
# As slots fill, urgency drops and other positions take over.
# ============================================================

PICK_PRIORITY = {
    'QB': 10, 'OL': 8,  'WR': 7,   'DE': 6.5, 'LB': 6,
    'CB': 5.5,'DT': 5,  'S':  5,   'RB': 4.5, 'TE': 4,
    'K':  2,  'P':  1,
}

def urgency(pos, remaining):
    if remaining <= 0:
        return -1
    return PICK_PRIORITY[pos] * (remaining / ROSTER_SLOTS[pos])

def choose_position(needs):
    """Return the position this team should draft next."""
    return max(
        (pos for pos, rem in needs.items() if rem > 0),
        key=lambda pos: urgency(pos, needs[pos]),
        default=None,
    )

# ============================================================
# TEAM BUILDER
# ============================================================

def build_teams():
    teams = []
    for conf, divisions in LEAGUE.items():
        for div, names in divisions.items():
            for name in names:
                teams.append({
                    'name':       name,
                    'conference': conf,
                    'division':   div,
                    'needs':      dict(ROSTER_SLOTS),
                    'roster':     defaultdict(list),
                })
    return teams

# ============================================================
# SNAKE DRAFT
# ============================================================

def snake_order(n_teams, n_rounds):
    """Yield (round_num, team_index) for a snake draft."""
    for r in range(n_rounds):
        order = range(n_teams) if r % 2 == 0 else range(n_teams - 1, -1, -1)
        for i in order:
            yield r + 1, i

def run_draft(teams, pool, show_rounds=2):
    """
    Run the CPU snake mega draft.
    show_rounds: print pick-by-pick output for the first N rounds only.
    Returns (teams_with_rosters, fa_pool).
    """
    available = {pos: list(players) for pos, players in pool.items()}
    n_rounds  = sum(ROSTER_SLOTS.values())  # 34 rounds
    pick_num  = 0

    print(f"  {'Pk':>3}  {'Rd':>3}  {'Team':<24}  {'Pos':<4}  {'Player':<22}  {'Age':>3}  {'Label'}")
    print(f"  {'-'*72}")

    for round_num, team_idx in snake_order(len(teams), n_rounds):
        team = teams[team_idx]
        pos  = choose_position(team['needs'])

        # Fallback: if top choice is depleted, take best available at any needed pos
        if pos is None or not available[pos]:
            pos = max(
                (p for p in available if available[p] and team['needs'].get(p, 0) > 0),
                key=lambda p: available[p][0]['composite'] if available[p] else 0,
                default=None,
            )
        if pos is None:
            continue

        player    = available[pos].pop(0)
        pick_num += 1
        team['roster'][pos].append(player)
        team['needs'][pos] -= 1

        if round_num <= show_rounds:
            print(f"  {pick_num:>3}  {round_num:>3}  {team['name']:<24}  "
                  f"{pos:<4}  {player['name']:<22}  {player['age']:>3}  "
                  f"{assign_label(player['composite'])}")

    if show_rounds < n_rounds:
        remaining_picks = n_rounds * len(teams) - show_rounds * len(teams)
        print(f"  ... ({remaining_picks} picks in rounds {show_rounds+1}-{n_rounds} not shown)")

    # Undrafted players become free agents
    fa_pool = {pos: players for pos, players in available.items() if players}
    return teams, fa_pool

# ============================================================
# COMPOSITE ROLLUP
# Mirrors the formula in football_sim.py
# ============================================================

WEIGHTS_6 = [0.30, 0.22, 0.18, 0.14, 0.10, 0.06]
WEIGHTS_3 = [0.50, 0.30, 0.20]

def player_composite(player):
    weights = WEIGHTS_3 if player['position'] in ('K', 'P') else WEIGHTS_6
    return sum(s * w for s, w in zip(player['stats'], weights))

def group_composite(players):
    """Starters (all but worst) averaged × 0.80 + backup × 0.20."""
    if not players:
        return 0.0
    comps   = sorted([player_composite(p) for p in players], reverse=True)
    starters = comps[:-1] if len(comps) > 1 else comps
    backup   = comps[-1]
    return 0.80 * (sum(starters) / len(starters)) + 0.20 * backup

def team_composites(team):
    """Return {position: group_composite} for all positions."""
    return {pos: group_composite(team['roster'][pos]) for pos in ROSTER_SLOTS}

# ============================================================
# DISPLAY
# ============================================================

def show_team(team):
    comps = team_composites(team)
    avg   = sum(comps.values()) / len(comps)
    print(f"\n  {team['name']:<24}  {team['conference']} | {team['division']}")
    print(f"  {'Pos':<5} {'Group':>7}  {'Players (label, age)'}")
    print(f"  {'-'*60}")
    for pos in ROSTER_SLOTS:
        players = sorted(team['roster'][pos], key=lambda p: p['composite'], reverse=True)
        summary = '  '.join(
            f"{p['name']} ({assign_label(p['composite'])},{p['age']})"
            for p in players
        )
        print(f"  {pos:<5} {comps[pos]:>7.1f}  {summary}")
    print(f"  {'Avg composite':.<25} {avg:.1f}")

def show_league_balance(teams):
    """Quick competitive balance view across all 16 teams."""
    print(f"\n{'='*55}")
    print(f"  League Competitive Balance")
    print(f"{'='*55}")
    print(f"  {'Team':<24}  {'Avg':>5}  {'Conf':<14}  Div")
    print(f"  {'-'*55}")
    ranked = sorted(teams, key=lambda t: sum(team_composites(t).values()), reverse=True)
    for t in ranked:
        avg = sum(team_composites(t).values()) / len(ROSTER_SLOTS)
        print(f"  {t['name']:<24}  {avg:>5.1f}  {t['conference']:<14}  {t['division']}")

def show_fa_pool(fa_pool):
    print(f"\n{'='*55}")
    print(f"  Free Agent Pool (undrafted)")
    print(f"{'='*55}")
    total = 0
    for pos in ROSTER_SLOTS:
        players = fa_pool.get(pos, [])
        if not players:
            continue
        comps = [p['composite'] for p in players]
        avg   = sum(comps) / len(comps)
        print(f"  {pos:<5} {len(players):>3} players   "
              f"avg {avg:.1f}   "
              f"best {max(comps):.1f} ({assign_label(max(comps))})")
        total += len(players)
    print(f"  {'-'*40}")
    print(f"  Total: {total} free agents")

# ============================================================
# SNAPSHOT
# ============================================================

def save_snapshot(teams, fa_pool, filepath='league_snapshot.txt'):
    lines = []

    def w(s=''):
        lines.append(s)

    w('=' * 70)
    w('  LEAGUE SNAPSHOT — Post Mega Draft')
    w('=' * 70)

    # Competitive balance table
    w()
    w(f"  {'Team':<26} {'Avg':>5}  {'Conf':<16} {'Div':<12} {'QB':>5}  {'OL':>5}  {'WR':>5}  {'D':>5}")
    w(f"  {'-'*68}")
    ranked = sorted(teams, key=lambda t: sum(team_composites(t).values()), reverse=True)
    for t in ranked:
        c   = team_composites(t)
        avg = sum(c.values()) / len(c)
        def_avg = (c['DT'] + c['DE'] + c['LB'] + c['CB'] + c['S']) / 5
        w(f"  {t['name']:<26} {avg:>5.1f}  {t['conference']:<16} {t['division']:<12} "
          f"{c['QB']:>5.1f}  {c['OL']:>5.1f}  {c['WR']:>5.1f}  {def_avg:>5.1f}")

    # Full team rosters
    w()
    w('=' * 70)
    w('  FULL ROSTERS')
    w('=' * 70)

    for conf, divisions in LEAGUE.items():
        w()
        w(f"  {conf.upper()}")
        for div, div_teams in divisions.items():
            w(f"  {div}")
            w(f"  {'-'*66}")
            for team in teams:
                if team['conference'] != conf or team['division'] != div:
                    continue
                c   = team_composites(team)
                avg = sum(c.values()) / len(c)
                w()
                w(f"  {team['name'].upper()}  (avg composite: {avg:.1f})")
                w(f"  {'Pos':<5} {'Grp':>5}  Players")
                w(f"  {'.'*64}")
                for pos in ROSTER_SLOTS:
                    players = sorted(team['roster'][pos],
                                     key=lambda p: p['composite'], reverse=True)
                    player_str = '   '.join(
                        f"{p['name']} ({assign_label(p['composite'])}, age {p['age']})"
                        for p in players
                    )
                    w(f"  {pos:<5} {c[pos]:>5.1f}  {player_str}")

    # FA pool
    w()
    w('=' * 70)
    w('  FREE AGENT POOL (undrafted)')
    w('=' * 70)
    total = 0
    for pos in ROSTER_SLOTS:
        players = fa_pool.get(pos, [])
        if not players:
            continue
        w()
        w(f"  {pos}  ({len(players)} players)")
        for p in sorted(players, key=lambda x: x['composite'], reverse=True):
            w(f"    {p['name']:<22} {assign_label(p['composite']):<12} age {p['age']}")
        total += len(players)
    w()
    w(f"  Total free agents: {total}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"\n  Snapshot saved to: {filepath}")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    random.seed(42)

    print("Generating player pool...")
    pool = generate_pool()

    print("Building teams...")
    teams = build_teams()

    n_rounds = sum(ROSTER_SLOTS.values())
    n_picks  = n_rounds * len(teams)
    print(f"\n{'='*75}")
    print(f"  CPU Snake Mega Draft | {len(teams)} teams | {n_rounds} rounds | {n_picks} total picks")
    print(f"{'='*75}\n")

    teams, fa_pool = run_draft(teams, pool, show_rounds=2)

    # Full team detail for first 2 teams
    print(f"\n\n{'='*65}")
    print(f"  Team Detail (sample - first 2 teams)")
    print(f"{'='*65}")
    for team in teams[:2]:
        show_team(team)

    # League balance
    show_league_balance(teams)

    # FA pool
    show_fa_pool(fa_pool)

    # Save full snapshot to file
    save_snapshot(teams, fa_pool, filepath='D:\\git\\football\\league_snapshot.txt')
