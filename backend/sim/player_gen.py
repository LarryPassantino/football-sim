import random
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================

TEAM_COUNT    = 16
FA_BUFFER_PCT = 0.15   # fraction above roster needs that goes to FA pool

POOL_TALENT_MEAN = 70.0
POOL_TALENT_STD  = 11.0

# Stat variance by priority rank — SKILL stat is tightest to base talent
SKILL_VARIANCE = 6    # stat 0 (SKILL)
MID_VARIANCE   = 9    # stats 1–2
DEEP_VARIANCE  = 12   # stats 3–5

# Correlation group bonus std dev — shared by stats in the same group
GROUP_BONUS_STD = 5


# ============================================================
# STAT LABEL SYSTEM
# ============================================================

LABEL_RANGES = [
    (83, 95, 'Elite'),
    (73, 82, 'Above Avg'),
    (63, 72, 'Average'),
    (50, 62, 'Below Avg'),
    (30, 49, 'Weak'),
]

def assign_label(value):
    for lo, hi, label in LABEL_RANGES:
        if lo <= value <= hi:
            return label
    return 'Weak' if value < 50 else 'Elite'


# ============================================================
# POSITION DEFINITIONS
# ============================================================

POSITION_STATS = {
    'QB': ['PASSING',      'AWARENESS', 'ARM',       'AGILITY',  'SPEED',    'STAMINA'],
    'WR': ['CATCHING',     'SPEED',     'ROUTE',     'AGILITY',  'STAMINA',  'STRENGTH'],
    'TE': ['CATCHING',     'BLOCK',     'STRENGTH',  'STAMINA',  'SPEED',    'AGILITY'],
    'RB': ['BREAK TACKLE', 'STRENGTH',  'CATCHING',  'SPEED',    'STAMINA',  'AGILITY'],
    'OL': ['BLOCK',        'STRENGTH',  'AWARENESS', 'AGILITY',  'STAMINA',  'SPEED'],
    'DT': ['DISRUPT',      'STRENGTH',  'TACKLE',    'STAMINA',  'AGILITY',  'SPEED'],
    'DE': ['PRESSURE',     'STRENGTH',  'AGILITY',   'SPEED',    'TACKLE',   'STAMINA'],
    'LB': ['TACKLE',       'STRENGTH',  'AGILITY',   'COVER',    'STAMINA',  'SPEED'],
    'CB': ['COVER',        'SPEED',     'AGILITY',   'TACKLE',   'STAMINA',  'STRENGTH'],
    'S':  ['COVER',        'SPEED',     'TACKLE',    'AGILITY',  'STRENGTH', 'STAMINA'],
    'K':  ['CLUTCH',       'ACCURACY',  'POWER'],
    'P':  ['PRECISION',    'POWER',     'AWARENESS'],
}

WEIGHTS_6 = [0.30, 0.22, 0.18, 0.14, 0.10, 0.06]
WEIGHTS_3 = [0.50, 0.30, 0.20]

ROSTER_SLOTS = {
    'QB': 2,  'WR': 4,  'TE': 2,  'RB': 2,  'OL': 6,
    'DT': 3,  'DE': 3,  'LB': 4,  'CB': 3,  'S':  3,
    'K':  1,  'P':  1,
}

# Stats that share a correlation bonus within each group
STAT_GROUPS = {
    'athletic': {'SPEED', 'AGILITY', 'ROUTE'},
    'physical': {'STRENGTH', 'STAMINA', 'BLOCK', 'TACKLE',
                 'DISRUPT', 'PRESSURE', 'BREAK TACKLE'},
    'mental':   {'AWARENESS', 'COVER', 'CLUTCH', 'PRECISION',
                 'ACCURACY', 'CATCHING'},
}
STAT_TO_GROUP = {s: g for g, stats in STAT_GROUPS.items() for s in stats}


# ============================================================
# NAMES
# ============================================================

FIRST_NAMES = [
    'Aaron', 'Andre', 'Blake', 'Brandon', 'Caleb', 'Cameron', 'Carlos', 'Chad',
    'Chris', 'Cole', 'Curtis', 'Damon', 'Dante', 'Darius', 'David', 'DeShawn',
    'Devon', 'Drew', 'Eli', 'Eric', 'Evan', 'Frank', 'Garrett', 'Greg',
    'Hunter', 'Isaiah', 'Jabari', 'Jalen', 'James', 'Jarvis', 'Jason', 'Jordan',
    'Josh', 'Justin', 'Kendall', 'Kevin', 'Kyle', 'Lance', 'Logan', 'Luke',
    'Marcus', 'Mark', 'Matt', 'Michael', 'Miles', 'Nathan', 'Nick', 'Omar',
    'Patrick', 'Quincy', 'Reggie', 'Rico', 'Riley', 'Robert', 'Ryan', 'Sam',
    'Seth', 'Shaun', 'Terrell', 'Thomas', 'Todd', 'Tony', 'Travis', 'Trevor',
    'Tyrone', 'Victor', 'Wes', 'Will', 'Xavier', 'Zach',
]

LAST_NAMES = [
    'Adams', 'Allen', 'Anderson', 'Armstrong', 'Bailey', 'Baker', 'Banks',
    'Bell', 'Bennett', 'Brooks', 'Brown', 'Bryant', 'Burke', 'Butler',
    'Carter', 'Clark', 'Coleman', 'Collins', 'Cook', 'Cooper', 'Cox',
    'Crawford', 'Cruz', 'Davis', 'Dixon', 'Edwards', 'Evans', 'Fields',
    'Fisher', 'Ford', 'Foster', 'Freeman', 'Garcia', 'Gibson', 'Graham',
    'Grant', 'Green', 'Griffin', 'Hall', 'Hamilton', 'Harris', 'Harrison',
    'Hayes', 'Henderson', 'Hill', 'Holmes', 'Howard', 'Hughes', 'Hunter',
    'Jackson', 'James', 'Jenkins', 'Johnson', 'Jones', 'Jordan', 'Kelly',
    'King', 'Knight', 'Lawrence', 'Lee', 'Lewis', 'Long', 'Martin',
    'Mason', 'Matthews', 'Miller', 'Mitchell', 'Moore', 'Morgan', 'Morris',
    'Murphy', 'Murray', 'Nelson', 'Owens', 'Parker', 'Patterson', 'Perry',
    'Peterson', 'Phillips', 'Porter', 'Powell', 'Price', 'Reed', 'Richardson',
    'Roberts', 'Robinson', 'Rogers', 'Ross', 'Russell', 'Sanders', 'Scott',
    'Shaw', 'Simmons', 'Smith', 'Spencer', 'Stewart', 'Stone', 'Sullivan',
    'Taylor', 'Thomas', 'Thompson', 'Turner', 'Walker', 'Ward', 'Warren',
    'Washington', 'Watson', 'White', 'Williams', 'Wilson', 'Wood', 'Wright',
    'Young',
]

def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


# ============================================================
# AGE
# ============================================================

# Weighted age distribution for initial league creation (staggered 21–33)
_AGE_WEIGHTS = {
    21: 4,  22: 6,  23: 8,           # raw — 18%
    24: 9,  25: 10, 26: 10, 27: 9,   # developing/peak — 38%
    28: 9,  29: 8,  30: 7,           # peak/early decline — 24%
    31: 7,  32: 6,  33: 7,           # veteran — 20%
}
_AGE_LIST    = list(_AGE_WEIGHTS.keys())
_AGE_WTS     = list(_AGE_WEIGHTS.values())

def random_age():
    return random.choices(_AGE_LIST, weights=_AGE_WTS)[0]

def age_modifier(age):
    """
    Rating shift based on age. Peak window is 25–28.
    Young players are raw (lower current rating, higher potential).
    Veterans are past peak (lower and declining).
    """
    if age <= 24:
        return (age - 25) * 1.8    # -1.8 at 24, -7.2 at 21
    elif age <= 28:
        return 0.0
    else:
        return -(age - 28) * 2.2   # -4.4 at 30, -11.0 at 33


# ============================================================
# PLAYER GENERATION
# ============================================================

def _clamp(v, lo, hi):
    return max(lo, min(hi, int(round(v))))

def generate_player(position, age=None):
    """
    Generate a single player at the given position.
    Returns a player dict with exact stats (hidden from opponents until owned).
    """
    if age is None:
        age = random_age()

    base_talent = random.gauss(POOL_TALENT_MEAN, POOL_TALENT_STD) + age_modifier(age)

    # Per-player correlation group bonuses — shared across stats in the same group
    group_bonus = {g: random.gauss(0, GROUP_BONUS_STD) for g in STAT_GROUPS}

    stat_names = POSITION_STATS[position]
    stats = []
    for i, stat_name in enumerate(stat_names):
        var  = SKILL_VARIANCE if i == 0 else (MID_VARIANCE if i <= 2 else DEEP_VARIANCE)
        corr = group_bonus.get(STAT_TO_GROUP.get(stat_name, ''), 0)
        stats.append(_clamp(base_talent + random.gauss(0, var) + corr, 30, 95))

    weights   = WEIGHTS_3 if position in ('K', 'P') else WEIGHTS_6
    composite = round(sum(s * w for s, w in zip(stats, weights)), 1)

    # Potential: theoretical peak (for v3 progression system)
    ceiling_bonus = max(0.0, (27 - age) * 1.2)
    potential = _clamp(composite + ceiling_bonus + random.gauss(4, 3), composite, 95)

    return {
        'name':      random_name(),
        'position':  position,
        'age':       age,
        'stats':     stats,       # exact — only visible when owned
        'composite': composite,   # exact — only visible when owned
        'potential': potential,   # exact — only visible when owned
        'injury_games_remaining': 0,
    }


def get_visible_stats(player, owned=False):
    """
    owned=True  → exact numbers (on your roster)
    owned=False → label strings (draft pool, FA pool, trade targets)
    """
    names = POSITION_STATS[player['position']]
    if owned:
        return {n: v for n, v in zip(names, player['stats'])}
    return {n: assign_label(v) for n, v in zip(names, player['stats'])}


def get_visible_composite(player, owned=False):
    if owned:
        return f"{player['composite']:.1f}"
    return assign_label(player['composite'])


# ============================================================
# POOL GENERATION
# ============================================================

def generate_pool(team_count=TEAM_COUNT, fa_buffer_pct=FA_BUFFER_PCT):
    """
    Generate a full player pool for league creation.
    Returns {position: [players sorted best→worst composite]}.
    """
    pool = {}
    for pos, slots in ROSTER_SLOTS.items():
        n_roster = slots * team_count
        n_fa     = max(2, int(n_roster * fa_buffer_pct))
        players  = [generate_player(pos) for _ in range(n_roster + n_fa)]
        players.sort(key=lambda p: p['composite'], reverse=True)
        pool[pos] = players
    return pool


# ============================================================
# DISPLAY
# ============================================================

def pool_summary(pool):
    """Distribution overview for the full generated pool."""
    label_order = [lbl for _, _, lbl in LABEL_RANGES]
    total = 0

    print(f"\n{'='*65}")
    print(f"  Player Pool | {TEAM_COUNT} teams  "
          f"({TEAM_COUNT * sum(ROSTER_SLOTS.values())} roster slots  "
          f"+ ~{int(TEAM_COUNT * sum(ROSTER_SLOTS.values()) * FA_BUFFER_PCT)} FA buffer)")
    print(f"{'='*65}")
    print(f"  {'Pos':<5} {'N':>5}  {'Avg':>5}  {'Lo':>4}  {'Hi':>4}  "
          f"{'Elite':>6}  {'AbvAvg':>7}  {'Avg':>5}  {'BlwAvg':>7}  {'Weak':>6}")
    print(f"  {'-'*62}")

    for pos in ROSTER_SLOTS:
        players    = pool[pos]
        composites = [p['composite'] for p in players]
        avg        = sum(composites) / len(composites)
        lc         = defaultdict(int)
        for c in composites:
            lc[assign_label(c)] += 1

        print(f"  {pos:<5} {len(players):>5}  {avg:>5.1f}  "
              f"{min(composites):>4.0f}  {max(composites):>4.0f}  "
              f"{lc['Elite']:>6}  {lc['Above Avg']:>7}  {lc['Average']:>5}  "
              f"{lc['Below Avg']:>7}  {lc['Weak']:>6}")
        total += len(players)

    print(f"  {'-'*62}")
    print(f"  {'TOTAL':<5} {total:>5}")


def show_player(player, owned=False):
    """Single player card — scout view or full view."""
    stats   = get_visible_stats(player, owned=owned)
    overall = get_visible_composite(player, owned=owned)
    tag     = 'ROSTER' if owned else 'SCOUT '
    pot     = f"  pot {player['potential']}" if owned else ''
    print(f"\n  [{tag}] {player['name']:<22} {player['position']:<3}  "
          f"Age {player['age']}  Overall: {overall}{pot}")
    for stat, val in stats.items():
        print(f"          {stat:<14} {val}")


def show_top(pool, position, n=8, owned=False):
    """Show the top N players at a position."""
    print(f"\n{'='*55}")
    print(f"  Top {n} {position}s  ({'exact' if owned else 'scout labels'})")
    print(f"{'='*55}")
    for p in pool[position][:n]:
        show_player(p, owned=owned)


def age_composite_chart(pool, position, n=20):
    """Quick age vs. composite view for a position."""
    print(f"\n{'='*55}")
    print(f"  {position} | age vs composite (top {n})")
    print(f"{'='*55}")
    for p in pool[position][:n]:
        bar = '#' * int(p['composite'] / 4)
        print(f"  Age {p['age']}  {p['composite']:5.1f}  {bar}")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    random.seed(42)

    pool = generate_pool()

    pool_summary(pool)

    # Scout view — what a coach sees at draft time
    show_top(pool, 'QB', n=6, owned=False)

    # Owned view — what you see after drafting the same players
    show_top(pool, 'QB', n=6, owned=True)

    # Age/composite spread
    age_composite_chart(pool, 'QB', n=20)
    age_composite_chart(pool, 'OL', n=20)
