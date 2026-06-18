import random
import math
from collections import defaultdict

# ============================================================
# TUNING PARAMETERS
# Adjust these to calibrate the sim without touching the logic.
# ============================================================

# --- Gate 1: Moving the ball (run game / early downs) ---
# Offense weights
G1_OFF_OL = 0.45
G1_OFF_RB = 0.25
G1_OFF_QB = 0.20  # mobility, scramble threat
G1_OFF_WR = 0.10  # blocking, releases

# Defense weights — DT dominates Gate 1 (run stuffing), DE is edge contain
G1_DEF_DT = 0.28
G1_DEF_DE = 0.12
G1_DEF_LB = 0.45
G1_DEF_S  = 0.15  # run support

# --- Gate 2: Finishing drives (passing / red zone) ---
# Offense weights
G2_OFF_QB = 0.45
G2_OFF_WR = 0.35
G2_OFF_RB = 0.10  # checkdowns, third-down catches
G2_OFF_OL = 0.10  # pass protection

# Defense weights — DE dominates Gate 2 (pass rush), DT provides interior pressure
G2_DEF_CB = 0.40
G2_DEF_DE = 0.22  # pass rush
G2_DEF_DT = 0.08  # interior pressure
G2_DEF_S  = 0.20
G2_DEF_LB = 0.10  # coverage LBs

# --- Base probabilities at rating parity (net = 0) ---
BASE_ADVANCE          = 0.47  # drive reaches scoring position
BASE_TD_GIVEN_ADVANCE = 0.45  # TD rate once in scoring position
BASE_TO_GIVEN_ADVANCE = 0.12  # turnover rate in scoring position
BASE_TO_GIVEN_STALL   = 0.15  # turnover rate on a stalled drive

# --- How much each net rating point shifts probabilities ---
ADV_SCALE = 0.009   # advance probability
TD_SCALE  = 0.007   # TD probability (gate 2)
TO_SCALE  = 0.002   # turnover probability (both gates)

# --- Kicker ---
BASE_FG_MAKE    = 0.80   # make rate at rating 70
FG_RATING_SCALE = 0.004  # per point above/below 70

# --- Game-day performance variance (two-layer modifier) ---
TEAM_DAY_SCALE = 4   # std dev of team-wide shift (weather, travel, emotion, cohesion)
UNIT_DAY_SCALE = 6   # std dev of per-unit shift on top of team factor

# --- Game settings ---
DRIVES_PER_TEAM = 12
AVERAGE_RATING  = 70

POSITION_GROUPS = ['qb', 'wr', 'rb', 'ol', 'dt', 'de', 'lb', 'cb', 's', 'k']

# --- Game plan composite modifiers (applied to flat team dict pre-sim) ---
# OFF plans shift the run/pass emphasis by boosting the relevant position groups.
# DEF plans shift run-stopping vs. pass-coverage priority.
_OFF_GAMEPLAN_MODS = {
    'balanced':   {},
    'run_focus':  {'ol': 1.08, 'rb': 1.07, 'qb': 0.97, 'wr': 0.97},
    'pass_focus': {'qb': 1.08, 'wr': 1.07, 'ol': 0.97, 'rb': 0.97},
}
_DEF_GAMEPLAN_MODS = {
    'balanced':  {},
    'run_stop':  {'dt': 1.08, 'lb': 1.06, 'cb': 0.95, 'de': 0.97},
    'pass_rush': {'de': 1.09, 'cb': 1.05, 'dt': 0.96, 'lb': 0.95},
}


def apply_gameplan(team: dict, off_plan: str = 'balanced', def_plan: str = 'balanced') -> dict:
    """Apply game plan multipliers to a flat team composite dict."""
    result = dict(team)
    for pos, mult in _OFF_GAMEPLAN_MODS.get(off_plan, {}).items():
        if pos in result:
            result[pos] = clamp(result[pos] * mult, 20, 99)
    for pos, mult in _DEF_GAMEPLAN_MODS.get(def_plan, {}).items():
        if pos in result:
            result[pos] = clamp(result[pos] * mult, 20, 99)
    return result


# ============================================================
# POSITION DEFINITIONS
# Stat names in priority order (index 0 = SKILL = most important).
# Weights apply positionally — same curve for all 6-stat positions.
# ============================================================

POSITION_STATS = {
    'QB': ['PASSING', 'AWARENESS', 'ARM',       'AGILITY', 'SPEED',   'STAMINA'],
    'WR': ['CATCHING','SPEED',     'ROUTE',     'AGILITY', 'STAMINA', 'STRENGTH'],
    'TE': ['CATCHING','BLOCK',     'STRENGTH',  'STAMINA', 'SPEED',   'AGILITY'],
    'RB': ['BREAK TACKLE','STRENGTH','CATCHING','SPEED',   'STAMINA', 'AGILITY'],
    'OL': ['BLOCK',   'STRENGTH',  'AWARENESS', 'AGILITY', 'STAMINA', 'SPEED'],
    'DT': ['DISRUPT', 'STRENGTH',  'TACKLE',    'STAMINA', 'AGILITY', 'SPEED'],
    'DE': ['PRESSURE','STRENGTH',  'AGILITY',   'SPEED',   'TACKLE',  'STAMINA'],
    'LB': ['TACKLE',  'STRENGTH',  'AGILITY',   'COVER',   'STAMINA', 'SPEED'],
    'CB': ['COVER',   'SPEED',     'AGILITY',   'TACKLE',  'STAMINA', 'STRENGTH'],
    'S':  ['COVER',   'SPEED',     'TACKLE',    'AGILITY', 'STRENGTH','STAMINA'],
    'K':  ['CLUTCH',  'ACCURACY',  'POWER'],
    'P':  ['PRECISION','POWER',    'AWARENESS'],
}

# KR uses these stats from whatever player is assigned (no dedicated roster slot)
KR_STATS = ['SPEED', 'AGILITY', 'STRENGTH', 'STAMINA']

# Weights by stat count — same descending curve, scaled to position
WEIGHTS_6 = [0.30, 0.22, 0.18, 0.14, 0.10, 0.06]  # all skill positions
WEIGHTS_3 = [0.50, 0.30, 0.20]                      # K, P

# Roster slots per position group
ROSTER_SLOTS = {
    'QB': {'starters': 1, 'backups': 1},
    'WR': {'starters': 3, 'backups': 2},
    'TE': {'starters': 1, 'backups': 1},
    'RB': {'starters': 1, 'backups': 2},
    'OL': {'starters': 5, 'backups': 1},
    'DT': {'starters': 2, 'backups': 2},
    'DE': {'starters': 2, 'backups': 2},
    'LB': {'starters': 3, 'backups': 2},
    'CB': {'starters': 2, 'backups': 2},
    'S':  {'starters': 2, 'backups': 2},
    'K':  {'starters': 1, 'backups': 0},
    'P':  {'starters': 1, 'backups': 0},
}
# Total roster: 34 players


# ============================================================
# TEAM DEFINITION (composite ratings, all 0–100)
# ============================================================

def make_team(name, qb, wr, rb, ol, dt, de, lb, cb, s, k):
    return dict(name=name, qb=qb, wr=wr, rb=rb, ol=ol,
                dt=dt, de=de, lb=lb, cb=cb, s=s, k=k)


# ============================================================
# COMPOSITE RATINGS
# Players will try to reverse-engineer these weights.
# Key hidden insight: DT matters more for Gate 1 (run defense),
# DE matters more for Gate 2 (pass rush).
# ============================================================

def gate1_off(t):
    return (t['ol']*G1_OFF_OL + t['rb']*G1_OFF_RB +
            t['qb']*G1_OFF_QB + t['wr']*G1_OFF_WR)

def gate1_def(t):
    return (t['dt']*G1_DEF_DT + t['de']*G1_DEF_DE +
            t['lb']*G1_DEF_LB + t['s']*G1_DEF_S)

def gate2_off(t):
    return (t['qb']*G2_OFF_QB + t['wr']*G2_OFF_WR +
            t['rb']*G2_OFF_RB + t['ol']*G2_OFF_OL)

def gate2_def(t):
    return (t['cb']*G2_DEF_CB + t['de']*G2_DEF_DE +
            t['dt']*G2_DEF_DT + t['s']*G2_DEF_S +
            t['lb']*G2_DEF_LB)


# ============================================================
# PLAYER & ROSTER ROLLUP
# ============================================================

def make_player(name, position, *stats, age=25):
    """
    Stats passed in priority order matching POSITION_STATS[position].
    e.g. make_player('Dan Marino', 'QB', 95, 88, 90, 70, 65, 75)
         = PASSING 95, AWARENESS 88, ARM 90, AGILITY 70, SPEED 65, STAMINA 75
    """
    return {'name': name, 'position': position, 'stats': list(stats), 'age': age}


def player_composite(player):
    """Weighted sum of a player's stats in priority order."""
    pos = player['position']
    weights = WEIGHTS_3 if pos in ('K', 'P') else WEIGHTS_6
    return sum(s * w for s, w in zip(player['stats'], weights))


def group_composite(starters, backup=None):
    """
    Average starter composites (all starters play significant snaps),
    then apply 80/20 split with the backup.
    No backup (K, P) returns starter average directly.
    """
    if not starters:
        return 0
    starter_avg = sum(player_composite(p) for p in starters) / len(starters)
    if backup is None:
        return starter_avg
    return 0.80 * starter_avg + 0.20 * player_composite(backup)


def make_team_from_roster(name, roster):
    """
    Build a sim-ready team dict from a full roster.

    roster format:
    {
        'QB': {'starters': [player, ...], 'backup': player or None},
        'WR': {'starters': [player, player, player], 'backup': player},
        ...
    }
    """
    def gc(pos):
        g = roster[pos]
        return group_composite(g['starters'], g.get('backup'))

    return make_team(
        name,
        qb = gc('QB'),
        wr = gc('WR'),
        rb = gc('RB'),
        ol = gc('OL'),
        dt = gc('DT'),
        de = gc('DE'),
        lb = gc('LB'),
        cb = gc('CB'),
        s  = gc('S'),
        k  = gc('K'),
    )


def show_roster_composites(name, roster):
    """Print each position group's composite rating for inspection."""
    print(f"\n{'='*55}")
    print(f"  Roster composites: {name}")
    print(f"{'='*55}")
    for pos, slots in ROSTER_SLOTS.items():
        g = roster[pos]
        starters = g['starters']
        backup   = g.get('backup')
        s_avg    = sum(player_composite(p) for p in starters) / len(starters)
        b_val    = f"{player_composite(backup):.1f}" if backup else '  n/a'
        gc       = group_composite(starters, backup)
        names    = ', '.join(p['name'] for p in starters)
        print(f"  {pos:<4} starter avg {s_avg:5.1f}  backup {b_val:>5}  group {gc:5.1f}  [{names}]")


# ============================================================
# DRIVE RESOLUTION
# ============================================================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def resolve_drive(offense, defense):
    """Returns (outcome_str, points)."""

    # Gate 1
    net1      = gate1_off(offense) - gate1_def(defense)
    p_advance = clamp(BASE_ADVANCE + net1 * ADV_SCALE, 0.20, 0.80)

    if random.random() > p_advance:
        p_to = clamp(BASE_TO_GIVEN_STALL - net1 * TO_SCALE, 0.04, 0.28)
        if random.random() < p_to:
            return 'turnover', 0
        return 'punt', 0

    # Gate 2
    net2 = gate2_off(offense) - gate2_def(defense)
    p_to = clamp(BASE_TO_GIVEN_ADVANCE - net2 * TO_SCALE, 0.03, 0.25)
    p_td = clamp(BASE_TD_GIVEN_ADVANCE + net2 * TD_SCALE, 0.20, 0.75)

    roll = random.random()
    if roll < p_to:
        return 'turnover', 0
    if roll < p_to + p_td:
        return 'touchdown', 7
    p_make = clamp(BASE_FG_MAKE + (offense['k'] - AVERAGE_RATING) * FG_RATING_SCALE, 0.40, 0.97)
    if random.random() < p_make:
        return 'field_goal', 3
    return 'missed_fg', 0


# ============================================================
# GAME-DAY PERFORMANCE MODIFIER
# ============================================================

def game_day_version(team):
    """
    Two-layer variance per game.
    Layer 1: team-wide factor (shared — cohesion, travel, weather)
    Layer 2: per-unit factor on top (independent unit variance)
    """
    team_factor = random.gauss(0, TEAM_DAY_SCALE)
    modified = dict(team)
    for pos in POSITION_GROUPS:
        unit_factor = random.gauss(0, UNIT_DAY_SCALE)
        modified[pos] = clamp(team[pos] + team_factor + unit_factor, 20, 99)
    return modified


# ============================================================
# GAME SIMULATION
# ============================================================

OT_PERIODS = 2  # max extra periods before a tie is declared

def simulate_game(team_a, team_b, is_playoff=False):
    a = game_day_version(team_a)
    b = game_day_version(team_b)

    score_a = score_b = 0
    outcomes_a = defaultdict(int)
    outcomes_b = defaultdict(int)
    scoring_plays = []
    drive_idx = 0  # overall drive counter across both teams; 6 drives per quarter

    def _record(team, out, pts):
        if pts > 0:
            quarter = min(drive_idx // 6 + 1, 4)
            scoring_plays.append({
                'team':    team,
                'type':    out,
                'score_a': score_a,
                'score_b': score_b,
                'quarter': quarter,
            })

    for _ in range(DRIVES_PER_TEAM):
        out, pts = resolve_drive(a, b)
        score_a += pts
        outcomes_a[out] += 1
        _record('a', out, pts)
        drive_idx += 1

        out, pts = resolve_drive(b, a)
        score_b += pts
        outcomes_b[out] += 1
        _record('b', out, pts)
        drive_idx += 1

    # Overtime: each team gets one drive per period, stop when someone leads
    for _ in range(OT_PERIODS):
        if score_a != score_b:
            break
        out, pts = resolve_drive(a, b)
        score_a += pts
        outcomes_a[out] += 1
        if pts > 0:
            scoring_plays.append({'team': 'a', 'type': out, 'score_a': score_a, 'score_b': score_b, 'quarter': 5})

        out, pts = resolve_drive(b, a)
        score_b += pts
        outcomes_b[out] += 1
        if pts > 0:
            scoring_plays.append({'team': 'b', 'type': out, 'score_a': score_a, 'score_b': score_b, 'quarter': 5})

    # Playoff games can't end in a tie — keep going until someone leads
    if is_playoff:
        while score_a == score_b:
            out, pts = resolve_drive(a, b)
            score_a += pts
            outcomes_a[out] += 1
            if pts > 0:
                scoring_plays.append({'team': 'a', 'type': out, 'score_a': score_a, 'score_b': score_b, 'quarter': 5})

            out, pts = resolve_drive(b, a)
            score_b += pts
            outcomes_b[out] += 1
            if pts > 0:
                scoring_plays.append({'team': 'b', 'type': out, 'score_a': score_a, 'score_b': score_b, 'quarter': 5})

    return score_a, score_b, outcomes_a, outcomes_b, scoring_plays


# ============================================================
# ANALYSIS TOOLS
# ============================================================

OUTCOME_ORDER = ['touchdown', 'field_goal', 'missed_fg', 'punt', 'turnover']

def validate_drives(offense, defense, n=10_000):
    outcomes  = defaultdict(int)
    total_pts = 0
    for _ in range(n):
        out, pts = resolve_drive(offense, defense)
        outcomes[out] += 1
        total_pts += pts
    print(f"\n{'='*55}")
    print(f"  {offense['name']} offense  vs  {defense['name']} defense")
    print(f"  {n:,} drives")
    print(f"{'='*55}")
    for k in OUTCOME_ORDER:
        pct = outcomes[k] / n * 100
        print(f"  {k:<14} {pct:5.1f}%  {'#'*int(pct/2)}")
    print(f"  {'avg pts/drive':<14} {total_pts/n:.2f}")
    print(f"  {'avg pts/game':<14} {total_pts/n*DRIVES_PER_TEAM:.1f}  (target: ~23)")


def score_distribution(team_a, team_b, n=5_000):
    scores_a, scores_b, diffs = [], [], []
    for _ in range(n):
        sa, sb, _, _ = simulate_game(team_a, team_b)
        scores_a.append(sa); scores_b.append(sb); diffs.append(abs(sa - sb))
    def stats(label, vals):
        mean = sum(vals) / len(vals)
        std  = (sum((v-mean)**2 for v in vals) / len(vals)) ** 0.5
        print(f"  {label:<22} avg {mean:5.1f}  std {std:4.1f}  min {min(vals):3}  max {max(vals):3}")
    print(f"\n{'='*55}")
    print(f"  Score distribution: {team_a['name']} vs {team_b['name']}  ({n:,} games)")
    print(f"{'='*55}")
    stats(team_a['name'], scores_a)
    stats(team_b['name'], scores_b)
    stats('margin of victory', diffs)


def head_to_head(team_a, team_b, n=10_000):
    wins_a = wins_b = ties = 0
    pts_a  = pts_b  = 0
    for _ in range(n):
        sa, sb, _, _ = simulate_game(team_a, team_b)
        pts_a += sa; pts_b += sb
        if   sa > sb: wins_a += 1
        elif sb > sa: wins_b += 1
        else:         ties   += 1
    print(f"\n{'='*55}")
    print(f"  Head to head: {team_a['name']} vs {team_b['name']}  ({n:,} games)")
    print(f"{'='*55}")
    print(f"  {team_a['name']:<22} {wins_a/n*100:5.1f}% wins  avg {pts_a/n:.1f} pts")
    print(f"  {team_b['name']:<22} {wins_b/n*100:5.1f}% wins  avg {pts_b/n:.1f} pts")
    print(f"  Ties                   {ties/n*100:5.1f}%")


def round_robin(teams, games_each=100):
    record = {t['name']: [0, 0, 0] for t in teams}
    pts    = {t['name']: [0, 0]    for t in teams}
    for i, a in enumerate(teams):
        for b in teams[i+1:]:
            for _ in range(games_each):
                sa, sb, _, _ = simulate_game(a, b)
                pts[a['name']][0] += sa;  pts[a['name']][1] += sb
                pts[b['name']][0] += sb;  pts[b['name']][1] += sa
                if   sa > sb: record[a['name']][0] += 1; record[b['name']][1] += 1
                elif sb > sa: record[b['name']][0] += 1; record[a['name']][1] += 1
                else:         record[a['name']][2] += 1; record[b['name']][2] += 1
    total_games = (len(teams) - 1) * games_each
    standings   = sorted(teams, key=lambda t: record[t['name']][0], reverse=True)
    print(f"\n{'='*55}")
    print(f"  Round Robin Standings  ({games_each} games vs each opponent)")
    print(f"{'='*55}")
    print(f"  {'Team':<22} {'W':>4} {'L':>4} {'T':>4}  {'PF/g':>6}  {'PA/g':>6}")
    print(f"  {'-'*50}")
    for t in standings:
        n = t['name']
        w, l, tie = record[n]
        pf = pts[n][0] / total_games
        pa = pts[n][1] / total_games
        print(f"  {n:<22} {w:>4} {l:>4} {tie:>4}  {pf:>6.1f}  {pa:>6.1f}")


# ============================================================
# MAIN — SCENARIOS
# ============================================================

if __name__ == '__main__':
    random.seed(42)

    # ---- Composite-level test teams (dt/de now separate) ----
    average  = make_team('Average',  qb=70, wr=70, rb=70, ol=70, dt=70, de=70, lb=70, cb=70, s=70, k=70)
    elite    = make_team('Elite',    qb=85, wr=85, rb=85, ol=85, dt=85, de=85, lb=85, cb=85, s=85, k=85)
    weak     = make_team('Weak',     qb=55, wr=55, rb=55, ol=55, dt=55, de=55, lb=55, cb=55, s=55, k=55)
    ol_team  = make_team('OL/Run',   qb=60, wr=65, rb=82, ol=88, dt=70, de=70, lb=70, cb=70, s=70, k=70)
    qb_team  = make_team('QB/Air',   qb=90, wr=82, rb=60, ol=55, dt=70, de=70, lb=70, cb=70, s=70, k=70)
    def_team = make_team('Def Wall', qb=65, wr=65, rb=65, ol=65, dt=85, de=85, lb=85, cb=85, s=85, k=70)

    # ---- Roster rollup example ----
    # Stats in POSITION_STATS priority order for each position
    example_roster = {
        'QB': {
            'starters': [make_player('A. Rivers',   'QB', 82, 85, 80, 68, 62, 74)],
            'backup':    make_player('B. Clipboard', 'QB', 58, 65, 60, 55, 58, 66),
        },
        'WR': {
            'starters': [
                make_player('C. Burnett',  'WR', 88, 82, 79, 80, 72, 60),
                make_player('D. Slater',   'WR', 78, 88, 72, 84, 68, 55),
                make_player('E. Cruz',     'WR', 80, 74, 85, 76, 70, 58),  # slot
            ],
            'backup':    make_player('F. Bench',    'WR', 62, 68, 60, 65, 60, 55),
        },
        'TE': {
            'starters': [make_player('G. Keller',   'TE', 80, 72, 75, 70, 65, 68)],
            'backup':    make_player('H. Block',     'TE', 60, 78, 70, 65, 60, 62),
        },
        'RB': {
            'starters': [make_player('I. Smash',    'RB', 84, 78, 72, 76, 74, 70)],
            'backup':    make_player('J. Spare',     'RB', 65, 65, 60, 70, 65, 62),
        },
        'OL': {
            'starters': [
                make_player('K. Wall',    'OL', 85, 82, 75, 70, 78, 60),
                make_player('L. Guard',   'OL', 80, 85, 70, 72, 75, 58),
                make_player('M. Center',  'OL', 78, 78, 85, 68, 72, 62),
                make_player('N. Guard',   'OL', 80, 83, 72, 70, 74, 58),
                make_player('O. Tackle',  'OL', 82, 80, 68, 75, 76, 60),
            ],
            'backup':    make_player('P. Swing',    'OL', 65, 68, 62, 60, 65, 55),
        },
        'DT': {
            'starters': [
                make_player('Q. Clog',    'DT', 82, 88, 78, 74, 68, 60),
                make_player('R. Stuff',   'DT', 78, 84, 80, 72, 65, 62),
            ],
            'backup':    make_player('S. Push',     'DT', 65, 72, 65, 65, 60, 58),
        },
        'DE': {
            'starters': [
                make_player('T. Rush',    'DE', 85, 78, 82, 80, 72, 68),
                make_player('U. Edge',    'DE', 80, 75, 78, 76, 70, 65),
            ],
            'backup':    make_player('V. Depth',    'DE', 65, 65, 66, 64, 62, 60),
        },
        'LB': {
            'starters': [
                make_player('W. Hit',     'LB', 84, 80, 76, 70, 72, 68),
                make_player('X. Chase',   'LB', 78, 75, 82, 72, 70, 72),
                make_player('Y. Cover',   'LB', 72, 70, 75, 85, 68, 74),  # coverage LB
            ],
            'backup':    make_player('Z. Back',     'LB', 65, 65, 65, 62, 65, 62),
        },
        'CB': {
            'starters': [
                make_player('AA. Lock',   'CB', 85, 88, 82, 72, 70, 60),
                make_player('BB. Press',  'CB', 80, 84, 78, 70, 68, 62),
            ],
            'backup':    make_player('CC. Zone',    'CB', 66, 72, 68, 62, 64, 58),
        },
        'S': {
            'starters': [
                make_player('DD. Free',   'S',  80, 84, 75, 78, 72, 70),
                make_player('EE. Strong', 'S',  78, 78, 82, 76, 74, 72),
            ],
            'backup':    make_player('FF. Deep',    'S',  68, 72, 68, 70, 65, 65),
        },
        'K': {
            'starters': [make_player('GG. Boot',    'K',  78, 82, 80)],
            'backup':    None,
        },
        'P': {
            'starters': [make_player('HH. Leg',     'P',  80, 84, 75)],
            'backup':    None,
        },
    }

    roster_team = make_team_from_roster('Example FC', example_roster)

    # ---- Output ----
    print('\n\n--- ROSTER ROLLUP ---')
    show_roster_composites('Example FC', example_roster)
    print(f"\n  Team dict: {roster_team}")

    print('\n\n--- DRIVE VALIDATION ---')
    validate_drives(average, average)
    validate_drives(elite,   weak)
    validate_drives(weak,    elite)

    print('\n\n--- ARCHETYPE MATCHUPS ---')
    validate_drives(ol_team, average)
    validate_drives(qb_team, average)

    print('\n\n--- SCORE VARIANCE ---')
    score_distribution(average, average)
    score_distribution(elite,   weak)

    print('\n\n--- HEAD TO HEAD ---')
    head_to_head(elite,    average)
    head_to_head(elite,    weak)
    head_to_head(ol_team,  qb_team)
    head_to_head(def_team, qb_team)
    head_to_head(roster_team, average)

    print('\n\n--- STANDINGS ---')
    all_teams = [average, elite, weak, ol_team, qb_team, def_team, roster_team]
    round_robin(all_teams, games_each=200)
