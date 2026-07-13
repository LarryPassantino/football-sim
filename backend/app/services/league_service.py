import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from functools import cmp_to_key

from sqlalchemy import delete, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sim.draft_sim import LEAGUE as LEAGUE_STRUCTURE, PICK_PRIORITY, build_teams, run_draft
from sim.player_gen import (
    generate_player, generate_pool, ROSTER_SLOTS,
    POSITION_STATS, WEIGHTS_3, WEIGHTS_6,
    annual_composite_delta, fitness_modifier, retirement_probability,
    _FA_DECLINE,
)
from sim.season_sim import build_schedule
from sim.training_sim import resolve_training_session, attainable_ceiling

from ..models import (
    Coach, Game, GameStatus, League, LeagueStatus,
    Player, PlayerGameStats, Season, SeasonStatus, Team,
)
from .sim_bridge import clear_all_injuries, play_game
from .push_service import send_game_result

REGULAR_SEASON_WEEKS = 17
OFFSEASON_DAYS       = 3
PLAYOFF_DIVISIONAL   = 18
PLAYOFF_CONF_CHAMP   = 19
PLAYOFF_LEAGUE_CHAMP = 20

# Training (v3 progression) — see training_and_potential.md
TRAIN_POINTS_PER_CYCLE       = 3   # per team, replenished each regular-season week
TRAIN_SESSIONS_PER_PLAYER    = 3   # per player, per season
MAX_TRAIN_POINTS_PER_SESSION = 3   # a single session can hold at most this many points
CPU_MAX_INTENSITY            = 2   # CPUs train at moderate intensity to limit self-injury


# ============================================================
# LEAGUE THEME FAMILIES
# Each family: league name + 6 member names (2 conferences, 4 divisions).
# Members are shuffled at league creation — conferences get [0-1], divisions [2-5].
# ============================================================

_THEME_FAMILIES = [
    {'league': 'Storm',     'members': ['Thunder',  'Lightning', 'Gale',    'Tempest', 'Squall',  'Cyclone']},
    {'league': 'Celestial', 'members': ['Nova',     'Pulsar',    'Eclipse', 'Aurora',  'Comet',   'Solaris']},
    {'league': 'Glacier',   'members': ['Summit',   'Crevasse',  'Ridge',   'Crest',   'Basin',   'Frost']},
    {'league': 'Ocean',     'members': ['Tide',     'Reef',      'Current', 'Surge',   'Shoal',   'Abyss']},
    {'league': 'Ember',     'members': ['Blaze',    'Cinder',    'Flare',   'Inferno', 'Smolder', 'Ash']},
    {'league': 'Iron',      'members': ['Anvil',    'Steel',     'Alloy',   'Temper',  'Slag',    'Ingot']},
    {'league': 'Thorn',     'members': ['Briar',    'Thistle',   'Nettle',  'Bramble', 'Sedge',   'Spine']},
    {'league': 'Dusk',      'members': ['Twilight', 'Ember',     'Shadow',  'Gloom',   'Murk',    'Haze']},
]


def _apply_league_theme(sim_teams: list) -> tuple[str, list]:
    """
    Pick a random theme, assign themed names to conference and division slots.
    Returns (league_name, sim_teams_with_themed_names).
    Conferences get the first 2 shuffled members; divisions get the remaining 4,
    assigned in the order (conf0/div0, conf0/div1, conf1/div0, conf1/div1).
    """
    theme   = random.choice(_THEME_FAMILIES)
    members = list(theme['members'])
    random.shuffle(members)

    # Collect unique (conference, division) pairs in encounter order
    conf_order: list[str] = []
    div_order:  list[tuple[str, str]] = []
    for t in sim_teams:
        if t['conference'] not in conf_order:
            conf_order.append(t['conference'])
        key = (t['conference'], t['division'])
        if key not in div_order:
            div_order.append(key)

    conf_map = {old: members[i]         for i, old in enumerate(conf_order)}
    div_map  = {key: members[2 + i]     for i, key in enumerate(div_order)}

    themed = [
        {**t,
         'conference': conf_map[t['conference']],
         'division':   div_map[(t['conference'], t['division'])]}
        for t in sim_teams
    ]
    return f"{theme['league']} League", themed


# ============================================================
# WEEK ASSIGNMENT
#
# Splitting the season's games into weeks is a graph edge-coloring problem:
# every team must appear exactly once per week (one game per week, no byes).
# The old code did randomized greedy bin-packing with a fallback that could
# SILENTLY DROP games it couldn't place. This version never drops a game — it
# either produces a perfect schedule or rebuilds the matchups and tries again,
# and a final validation pass guarantees correctness before it's ever persisted.
# ============================================================

class ScheduleError(Exception):
    """Raised when a set of matchups cannot be colored into a valid weekly schedule."""


def _greedy_color(games: list[tuple], n_weeks: int, games_per_week: int) -> dict[int, list] | None:
    """Fast path: one randomized greedy pass. Returns None if any game can't be placed."""
    games = list(games)
    random.shuffle(games)
    weeks: dict[int, list] = {w: [] for w in range(1, n_weeks + 1)}
    booked: dict[int, set] = {w: set() for w in range(1, n_weeks + 1)}
    for h, a in games:
        for w in range(1, n_weeks + 1):
            if len(weeks[w]) < games_per_week and h not in booked[w] and a not in booked[w]:
                weeks[w].append((h, a))
                booked[w].add(h)
                booked[w].add(a)
                break
        else:
            return None  # no legal week for this game — this arrangement failed
    return weeks


def _backtrack_color(games: list[tuple], n_weeks: int, games_per_week: int,
                     budget: int = 2_000_000) -> dict[int, list] | None:
    """
    Guaranteed path: complete backtracking search. If any valid coloring exists
    it will be found (within the node budget). Returns None only if the matchup
    set is genuinely un-colorable (or the budget is exhausted) — the caller then
    rebuilds the matchups. Parallel games (division home-and-home) are grouped
    adjacently so the tight constraints prune the search early, and empty weeks
    are treated as interchangeable to kill symmetric branches.
    """
    games = sorted(games, key=lambda g: (min(g), max(g)))
    weeks: dict[int, list] = {w: [] for w in range(1, n_weeks + 1)}
    booked: dict[int, set] = {w: set() for w in range(1, n_weeks + 1)}
    nodes = [budget]

    def place(i: int, opened: int) -> bool:
        if i == len(games):
            return True
        if nodes[0] <= 0:
            return False
        nodes[0] -= 1
        h, a = games[i]
        limit = min(opened + 1, n_weeks)  # only one fresh (empty) week per step
        for w in range(1, limit + 1):
            if len(weeks[w]) < games_per_week and h not in booked[w] and a not in booked[w]:
                weeks[w].append((h, a))
                booked[w].add(h)
                booked[w].add(a)
                if place(i + 1, max(opened, w)):
                    return True
                weeks[w].pop()
                booked[w].discard(h)
                booked[w].discard(a)
        return False

    return weeks if place(0, 0) else None


def _validate_weeks(weeks: dict[int, list], n_teams: int, n_weeks: int, games_per_week: int) -> None:
    """Hard guarantee: every week is full, no team plays twice, every team plays every week."""
    played: dict[int, int] = defaultdict(int)
    for w in range(1, n_weeks + 1):
        assert len(weeks[w]) == games_per_week, f'week {w} has {len(weeks[w])} games, expected {games_per_week}'
        seen: set = set()
        for h, a in weeks[w]:
            assert h not in seen and a not in seen, f'team plays twice in week {w}'
            seen.add(h)
            seen.add(a)
            played[h] += 1
            played[a] += 1
    for t in range(n_teams):
        assert played[t] == n_weeks, f'team {t} plays {played[t]} games, expected {n_weeks}'


def _build_weekly_schedule(sim_teams: list, n_weeks: int = REGULAR_SEASON_WEEKS,
                           max_regen: int = 50) -> dict[int, list[tuple]]:
    """
    Build a matchup set and color it into weeks, guaranteeing a full n_weeks-game
    schedule with no dropped games. Rebuilds the matchups if a given arrangement
    can't be colored. Raises ScheduleError only if it exhausts every attempt.
    """
    for _ in range(max_regen):
        schedule = build_schedule(sim_teams)
        games_per_week = len(schedule) // n_weeks

        weeks = None
        for _ in range(200):                      # fast randomized greedy
            weeks = _greedy_color(schedule, n_weeks, games_per_week)
            if weeks is not None:
                break
        if weeks is None:                          # complete search fallback
            weeks = _backtrack_color(schedule, n_weeks, games_per_week)

        if weeks is not None:
            _validate_weeks(weeks, len(sim_teams), n_weeks, games_per_week)
            return weeks

    raise ScheduleError(f'could not build a valid {n_weeks}-week schedule after {max_regen} attempts')


# ============================================================
# LEAGUE CREATION
# ============================================================

async def create_league(db: AsyncSession, name: str) -> League:
    pool      = generate_pool()
    sim_teams = build_teams()
    sim_teams, fa_pool = run_draft(sim_teams, pool, show_rounds=0)

    league_name, sim_teams = _apply_league_theme(sim_teams)
    league = League(name=league_name)
    db.add(league)
    await db.flush()

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

    season = Season(league_id=league.id, season_number=1, current_week=1)
    db.add(season)
    await db.flush()

    weeks = _build_weekly_schedule(sim_teams)

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
# STANDINGS + PLAYOFF SEEDING
# ============================================================

async def _get_standings(db: AsyncSession, season: Season) -> dict[uuid.UUID, dict]:
    """W/L record, point differential, and head-to-head for every team. Regular season only."""
    result = await db.execute(select(Team).where(Team.league_id == season.league_id))
    teams  = result.scalars().all()

    standings = {
        t.id: {
            'team_id':    t.id,
            'name':       t.name,
            'conference': t.conference,
            'division':   t.division,
            'wins':       0,
            'losses':     0,
            'point_diff': 0,
            'h2h':        defaultdict(int),  # h2h[opponent_id] = wins vs that opponent
        }
        for t in teams
    }

    result = await db.execute(
        select(Game).where(
            Game.season_id   == season.id,
            Game.status      == GameStatus.complete,
            Game.is_playoff  == False,
        )
    )
    for game in result.scalars().all():
        home   = standings[game.home_team_id]
        away   = standings[game.away_team_id]
        margin = game.home_score - game.away_score

        home['point_diff'] += margin
        away['point_diff'] -= margin

        if margin > 0:
            home['wins']   += 1
            away['losses'] += 1
            home['h2h'][game.away_team_id] += 1
        else:
            home['losses'] += 1
            away['wins']   += 1
            away['h2h'][game.home_team_id] += 1

    return standings


def _compare_teams(a: dict, b: dict) -> int:
    """
    Comparator for seeding: negative = a ranks higher.
    Tiebreakers: wins > head-to-head > point differential > coin flip.
    """
    if a['wins'] != b['wins']:
        return b['wins'] - a['wins']

    h2h_a = a['h2h'].get(b['team_id'], 0)
    h2h_b = b['h2h'].get(a['team_id'], 0)
    if h2h_a != h2h_b:
        return h2h_b - h2h_a

    if a['point_diff'] != b['point_diff']:
        return b['point_diff'] - a['point_diff']

    return random.choice([-1, 1])


def _seed_conference(standings: dict, conference: str) -> list[dict]:
    """
    Returns 4 playoff seeds for a conference, ordered #1→#4.
    Division winners guaranteed in; seeds determined purely by record (with tiebreakers).
    """
    conf_teams = [t for t in standings.values() if t['conference'] == conference]

    divisions = defaultdict(list)
    for t in conf_teams:
        divisions[t['division']].append(t)

    div_winners    = [sorted(teams, key=cmp_to_key(_compare_teams))[0] for teams in divisions.values()]
    div_winner_ids = {t['team_id'] for t in div_winners}

    wild_cards = sorted(
        [t for t in conf_teams if t['team_id'] not in div_winner_ids],
        key=cmp_to_key(_compare_teams),
    )[:2]

    return sorted(div_winners + wild_cards, key=cmp_to_key(_compare_teams))


# ============================================================
# CPU ROSTER MANAGEMENT
# ============================================================

_POSITION_MAX_ACTIVE = {
    'QB': 2, 'WR': 4, 'TE': 2, 'RB': 2, 'OL': 6,
    'DT': 3, 'DE': 3, 'LB': 4, 'CB': 3, 'S': 3,
    'K': 1, 'P': 1,
}


_FA_MINIMUM = 2  # per position, per league


async def _ensure_fa_minimums(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Generate new players for any position with fewer than _FA_MINIMUM free agents."""
    for pos in ROSTER_SLOTS:
        result = await db.execute(
            select(func.count()).where(
                Player.league_id == league_id,
                Player.team_id.is_(None),
                Player.position  == pos,
                Player.retired   == False,  # noqa: E712
            )
        )
        fa_count = result.scalar()
        for _ in range(_FA_MINIMUM - fa_count):
            p = generate_player(pos)
            db.add(Player(
                league_id=league_id,
                team_id=None,
                name=p['name'],
                position=pos,
                age=p['age'],
                stats=p['stats'],
                composite=p['composite'],
                potential=p['potential'],
            ))


async def run_cpu_roster_moves(db: AsyncSession, season: Season) -> None:
    """
    After each game tick, CPU teams:
      1. Activate any fully recovered IR players (drop weakest active at same position).
      2. Sign the best available FA for any position slot still under the active max.
    Human teams are skipped — they manage their own rosters.
    """
    league_id = season.league_id

    result = await db.execute(
        select(Team).where(Team.league_id == league_id, Team.is_cpu == True)  # noqa: E712
    )
    cpu_teams = result.scalars().all()

    for team in cpu_teams:
        # ── Step 1: activate recovered IR players ────────────────────────────
        result = await db.execute(
            select(Player).where(
                Player.team_id               == team.id,
                Player.on_ir                 == True,   # noqa: E712
                Player.injury_games_remaining == 0,
            )
        )
        recovered = result.scalars().all()

        for ir_player in recovered:
            # Drop the weakest active player at the same position
            result = await db.execute(
                select(Player)
                .where(
                    Player.team_id  == team.id,
                    Player.on_ir    == False,  # noqa: E712
                    Player.position == ir_player.position,
                )
                .order_by(Player.composite.asc())
                .limit(1)
            )
            drop = result.scalar_one_or_none()
            if drop:
                drop.team_id = None
                drop.on_ir   = False
            ir_player.on_ir = False

        # Flush so dropped players appear as free agents in the next query
        await db.flush()

        # ── Step 2: fill open active slots with best available FA ─────────────
        for pos, max_count in _POSITION_MAX_ACTIVE.items():
            result = await db.execute(
                select(func.count()).where(
                    Player.team_id  == team.id,
                    Player.on_ir    == False,  # noqa: E712
                    Player.position == pos,
                )
            )
            active_count = result.scalar()
            if active_count >= max_count:
                continue

            result = await db.execute(
                select(Player)
                .where(
                    Player.league_id == league_id,
                    Player.team_id.is_(None),
                    Player.position  == pos,
                    Player.retired   == False,  # noqa: E712
                )
                .order_by(Player.composite.desc())
                .limit(1)
            )
            fa = result.scalar_one_or_none()
            if fa:
                fa.team_id = team.id
                fa.on_ir   = False

    await _ensure_fa_minimums(db, league_id)


# ============================================================
# SCHEDULE REPAIR
# ============================================================

async def repair_season_schedule(db: AsyncSession, league_id: uuid.UUID) -> dict:
    """
    Fill accidental bye weeks caused by _assign_weeks dropping games at season creation.
    Only fixes future weeks (>= current_week) — past byes are permanent.
    """
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id, Season.status == SeasonStatus.regular)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    if not season:
        return {'error': 'no active regular season'}

    result = await db.execute(select(Team).where(Team.league_id == league_id))
    all_teams = list(result.scalars().all())

    result = await db.execute(
        select(Game).where(Game.season_id == season.id, Game.is_playoff == False)  # noqa: E712
    )
    week_teams: dict[int, set] = defaultdict(set)
    for g in result.scalars().all():
        week_teams[g.week].add(g.home_team_id)
        week_teams[g.week].add(g.away_team_id)

    added = 0
    for week in range(season.current_week, REGULAR_SEASON_WEEKS + 1):
        free = [t for t in all_teams if t.id not in week_teams[week]]
        random.shuffle(free)
        for i in range(0, len(free) - 1, 2):
            home, away = free[i], free[i + 1]
            db.add(Game(
                season_id=season.id,
                week=week,
                home_team_id=home.id,
                away_team_id=away.id,
            ))
            week_teams[week].add(home.id)
            week_teams[week].add(away.id)
            added += 1

    return {'makeup_games_added': added}


# ============================================================
# WEEK ADVANCEMENT
# ============================================================

async def advance_week(db: AsyncSession, league_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(Season).where(
            Season.league_id == league_id,
            Season.status.in_([SeasonStatus.regular, SeasonStatus.playoffs]),
        )
    )
    season = result.scalar_one_or_none()
    if not season:
        return {'skipped': True, 'reason': 'no active season'}

    if season.status == SeasonStatus.regular:
        return await _advance_regular_week(db, season)
    return await _advance_playoff_week(db, season)


async def _notify_game_result(db: AsyncSession, game: Game) -> None:
    """Send push notification to any human coach involved in this game."""
    for team, my_score, opp_score, opponent in [
        (game.home_team, game.home_score, game.away_score, game.away_team.name),
        (game.away_team, game.away_score, game.home_score, game.home_team.name),
    ]:
        if not team.coach_id:
            continue
        coach = await db.get(Coach, team.coach_id)
        if not coach:
            continue
        if not coach.fcm_token:
            print(f'[push] Coach {coach.id} ({team.name}) has no FCM token — skipping')
            continue
        send_game_result(coach.fcm_token, team.name, my_score, opp_score, opponent)


async def _cpu_train_team(db: AsyncSession, team: Team, season: Season) -> None:
    """Spend a CPU team's weekly training points on its youngest, highest-headroom
    players at moderate intensity. Mirrors the human rules: session cap, one session
    per player per cycle, no training the injured."""
    result = await db.execute(
        select(Player).where(Player.team_id == team.id, Player.retired == False)  # noqa: E712
    )
    players = result.scalars().all()

    def headroom(p):
        return attainable_ceiling(p.age, p.potential) - p.composite

    def eligible(p):
        return (
            p.injury_games_remaining == 0 and not p.on_ir
            and p.train_sessions_used < TRAIN_SESSIONS_PER_PLAYER
            and p.trained_in_week != season.current_week
            and headroom(p) > 0
        )

    # Prefer high headroom, skew toward youth.
    candidates = sorted(
        (p for p in players if eligible(p)),
        key=lambda p: headroom(p) * (1 + max(0, 27 - p.age) * 0.1),
        reverse=True,
    )

    points = team.train_points
    for p in candidates:
        if points <= 0:
            break
        intensity = min(CPU_MAX_INTENSITY, points)
        res = resolve_training_session(
            stats=p.stats, composite=p.composite, potential=p.potential,
            position=p.position, age=p.age, intensity=intensity,
        )
        p.stats     = list(res.stats)
        p.composite = res.composite
        if res.outcome == 'injury':
            p.injury_games_remaining = res.injury_games
        p.train_sessions_used += 1
        p.trained_in_week      = season.current_week
        points -= intensity
    team.train_points = points


async def _open_training_cycle(db: AsyncSession, season: Season) -> None:
    """Open a new regular-season training cycle: refresh every team's point budget
    (use-it-or-lose-it) and let CPU teams spend theirs immediately. Human coaches
    spend during the wait before the next game tick."""
    result = await db.execute(select(Team).where(Team.league_id == season.league_id))
    teams = result.scalars().all()
    for team in teams:
        team.train_points = TRAIN_POINTS_PER_CYCLE
    for team in teams:
        if team.is_cpu:
            await _cpu_train_team(db, team, season)


async def _advance_regular_week(db: AsyncSession, season: Season) -> dict:
    # CPU roster moves run at the start of each week so human coaches get
    # first access to FAs after the previous week's injuries resolved.
    await run_cpu_roster_moves(db, season)

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
        await play_game(
            db, game, game.home_team, game.away_team, games_remaining,
            home_off_plan=game.home_team.off_gameplan,
            home_def_plan=game.home_team.def_gameplan,
            away_off_plan=game.away_team.off_gameplan,
            away_def_plan=game.away_team.def_gameplan,
        )
        game.home_team.off_gameplan = 'balanced'
        game.home_team.def_gameplan = 'balanced'
        game.away_team.off_gameplan = 'balanced'
        game.away_team.def_gameplan = 'balanced'
        await _notify_game_result(db, game)

    season.current_week += 1

    if season.current_week > REGULAR_SEASON_WEEKS:
        standings  = await _get_standings(db, season)
        conferences = list({t['conference'] for t in standings.values()})

        for conf in conferences:
            seeds = _seed_conference(standings, conf)
            # #1 hosts #4, #2 hosts #3
            db.add(Game(season_id=season.id, week=PLAYOFF_DIVISIONAL,
                        home_team_id=seeds[0]['team_id'], away_team_id=seeds[3]['team_id'],
                        is_playoff=True))
            db.add(Game(season_id=season.id, week=PLAYOFF_DIVISIONAL,
                        home_team_id=seeds[1]['team_id'], away_team_id=seeds[2]['team_id'],
                        is_playoff=True))

        season.status = SeasonStatus.playoffs
    else:
        # New regular-season cycle opens: refresh training budgets and let CPUs develop.
        await _open_training_cycle(db, season)

    await db.commit()
    return {'week_played': season.current_week - 1, 'games': len(games)}


async def _advance_playoff_week(db: AsyncSession, season: Season) -> dict:
    await run_cpu_roster_moves(db, season)

    games_remaining_map = {
        PLAYOFF_DIVISIONAL:   3,
        PLAYOFF_CONF_CHAMP:   2,
        PLAYOFF_LEAGUE_CHAMP: 1,
    }

    result = await db.execute(
        select(Game)
        .where(
            Game.season_id  == season.id,
            Game.week       == season.current_week,
            Game.is_playoff == True,
        )
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
    )
    games = result.scalars().all()

    gr = games_remaining_map.get(season.current_week, 1)
    for game in games:
        if game.status == GameStatus.complete:
            continue
        await play_game(
            db, game, game.home_team, game.away_team, gr,
            home_off_plan=game.home_team.off_gameplan,
            home_def_plan=game.home_team.def_gameplan,
            away_off_plan=game.away_team.off_gameplan,
            away_def_plan=game.away_team.def_gameplan,
        )
        game.home_team.off_gameplan = 'balanced'
        game.home_team.def_gameplan = 'balanced'
        game.away_team.off_gameplan = 'balanced'
        game.away_team.def_gameplan = 'balanced'
        await _notify_game_result(db, game)

    if season.current_week == PLAYOFF_DIVISIONAL:
        # Group by conference, create one conf championship game per conference
        conf_games: dict[str, list] = defaultdict(list)
        for game in games:
            conf_games[game.home_team.conference].append(game)

        for conf, cg in conf_games.items():
            winners = [
                g.home_team_id if g.home_score > g.away_score else g.away_team_id
                for g in cg
            ]
            db.add(Game(season_id=season.id, week=PLAYOFF_CONF_CHAMP,
                        home_team_id=winners[0], away_team_id=winners[1],
                        is_playoff=True))

        season.current_week = PLAYOFF_CONF_CHAMP

    elif season.current_week == PLAYOFF_CONF_CHAMP:
        winners = [
            g.home_team_id if g.home_score > g.away_score else g.away_team_id
            for g in games
        ]
        db.add(Game(season_id=season.id, week=PLAYOFF_LEAGUE_CHAMP,
                    home_team_id=winners[0], away_team_id=winners[1],
                    is_playoff=True))

        season.current_week = PLAYOFF_LEAGUE_CHAMP

    elif season.current_week == PLAYOFF_LEAGUE_CHAMP:
        await db.commit()
        await end_season(db, season.league_id)
        return {'week_played': PLAYOFF_LEAGUE_CHAMP, 'games': len(games), 'champion': True}

    await db.commit()
    return {'week_played': season.current_week - 1, 'games': len(games)}


# ============================================================
# END SEASON
# ============================================================

_STAT_FIELDS = [
    'pass_attempts', 'pass_completions', 'pass_yards', 'pass_tds', 'interceptions_thrown',
    'rush_attempts', 'rush_yards', 'rush_tds',
    'receptions', 'receiving_yards', 'receiving_tds',
    'fumbles', 'fumbles_lost', 'sacks_allowed',
    'tackles', 'sacks', 'interceptions', 'forced_fumbles', 'fumble_recoveries',
]


async def apply_aging(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Age all non-retired players, apply composite delta, retire where appropriate."""
    result = await db.execute(
        select(Player).where(
            Player.league_id == league_id,
            Player.retired   == False,  # noqa: E712
        )
    )
    players = result.scalars().all()

    for player in players:
        is_fa   = player.team_id is None
        weights = WEIGHTS_3 if player.position in ('K', 'P') else WEIGHTS_6

        delta = (
            annual_composite_delta(player.age)
            + fitness_modifier(player.stats, player.position)
            + random.gauss(0, 1.5)
        )
        if is_fa:
            delta -= _FA_DECLINE

        new_stats = [
            max(30, min(95, int(round(s + delta + random.gauss(0, 1.0)))))
            for s in player.stats
        ]
        new_composite = round(sum(s * w for s, w in zip(new_stats, weights)), 1)

        # Natural growth carries a player toward — never past — his potential.
        # Weights sum to 1.0, so shaving the overshoot off every stat lands
        # composite at potential. (Decline never triggers this branch.)
        if new_composite > player.potential:
            overshoot = new_composite - player.potential
            new_stats = [max(30, int(round(s - overshoot))) for s in new_stats]
            new_composite = round(sum(s * w for s, w in zip(new_stats, weights)), 1)

        if random.random() < retirement_probability(player.age + 1, new_composite):
            player.retired = True
            player.team_id = None
            player.on_ir   = False
        else:
            player.age       = player.age + 1
            player.stats     = list(new_stats)
            player.composite = new_composite
            player.train_sessions_used = 0   # fresh training sessions each season
            player.trained_in_week     = 0

    await _ensure_fa_minimums(db, league_id)


async def end_season(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Accumulate season stats into career totals, clear injuries, move league to offseason."""
    result = await db.execute(select(League).where(League.id == league_id))
    league = result.scalar_one()

    result = await db.execute(
        select(Season).where(Season.league_id == league_id, Season.status != SeasonStatus.complete)
    )
    season = result.scalar_one_or_none()

    if season:
        # Aggregate all PlayerGameStats for this season grouped by player
        agg_result = await db.execute(
            select(
                PlayerGameStats.player_id,
                *[func.sum(getattr(PlayerGameStats, f)).label(f) for f in _STAT_FIELDS],
            )
            .join(Game, PlayerGameStats.game_id == Game.id)
            .where(Game.season_id == season.id)
            .group_by(PlayerGameStats.player_id)
        )
        rows = agg_result.all()

        for row in rows:
            player = await db.get(Player, row.player_id)
            if not player:
                continue
            career = dict(player.career_stats or {})
            for f in _STAT_FIELDS:
                career[f] = career.get(f, 0) + int(getattr(row, f) or 0)
            player.career_stats = career

        season.status       = SeasonStatus.complete
        season.completed_at = datetime.now(timezone.utc)

    await clear_all_injuries(db, league_id)
    await apply_aging(db, league_id)
    league.status = LeagueStatus.offseason
    await db.commit()

    # Generate draft class immediately so coaches have the full offseason to scout
    await generate_annual_draft_class(db, league_id)


async def start_new_season(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Create season N+1 with a fresh schedule. Players keep their current rosters."""
    result = await db.execute(select(League).where(League.id == league_id))
    league = result.scalar_one()

    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    last_season = result.scalar_one()

    result = await db.execute(
        select(Team).where(Team.league_id == league_id).order_by(Team.id)
    )
    teams = result.scalars().all()
    for t in teams:
        t.train_points = TRAIN_POINTS_PER_CYCLE   # fresh weekly budget for the new season

    sim_teams      = [{'conference': t.conference, 'division': t.division} for t in teams]
    team_idx_to_id = {i: t.id for i, t in enumerate(teams)}

    new_season = Season(
        league_id=league_id,
        season_number=last_season.season_number + 1,
        current_week=1,
    )
    db.add(new_season)
    await db.flush()

    weeks = _build_weekly_schedule(sim_teams)

    for week_num, games in weeks.items():
        for h_idx, a_idx in games:
            db.add(Game(
                season_id=new_season.id,
                week=week_num,
                home_team_id=team_idx_to_id[h_idx],
                away_team_id=team_idx_to_id[a_idx],
            ))

    league.status = LeagueStatus.regular
    await db.commit()


# ============================================================
# ANNUAL DRAFT
# ============================================================

DRAFT_ROUNDS     = 5
DRAFT_CLASS_SIZE = 160
DRAFT_CLASS_AGES = [21, 21, 22, 22, 22, 23, 23, 23]
DRAFT_TOLERANCE  = 5.0   # composite points; within this, follow position priority
PRESEASON_DAYS   = 2

FA_MAX_PER_POSITION = {
    'K': 6,  'P': 6,
    'TE': 8, 'RB': 8,
    'QB': 10, 'DT': 10, 'DE': 10, 'CB': 10, 'S': 10,
    'WR': 12, 'OL': 12, 'LB': 12,
}


async def _draft_order_from_standings(db: AsyncSession, league_id: uuid.UUID) -> list[uuid.UUID]:
    """
    Return team IDs in draft order (worst pick first).
    Non-playoff teams: sorted by regular-season record (worst first).
    Playoff teams: grouped by elimination round (earlier exit = earlier pick),
    sorted by record within each round. Champion picks last.
    """
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id, Season.status == SeasonStatus.complete)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if not last:
        result = await db.execute(select(Team).where(Team.league_id == league_id).order_by(Team.id))
        return [t.id for t in result.scalars().all()]

    standings = await _get_standings(db, last)

    # Determine playoff elimination round for each team
    result = await db.execute(
        select(Game).where(
            Game.season_id  == last.id,
            Game.is_playoff == True,   # noqa: E712
            Game.status     == GameStatus.complete,
        )
    )
    playoff_games = result.scalars().all()

    eliminated_in: dict[uuid.UUID, int] = {}
    champion_id:   uuid.UUID | None = None
    for g in playoff_games:
        winner_id = g.home_team_id if g.home_score > g.away_score else g.away_team_id
        loser_id  = g.away_team_id if g.home_score > g.away_score else g.home_team_id
        eliminated_in[loser_id] = g.week
        if g.week == PLAYOFF_LEAGUE_CHAMP:
            champion_id = winner_id

    playoff_team_ids = set(eliminated_in) | ({champion_id} if champion_id else set())

    def _sort_worst_first(team_ids: list) -> list[uuid.UUID]:
        rows = [standings[tid] for tid in team_ids if tid in standings]
        rows.sort(key=cmp_to_key(_compare_teams))  # best→worst
        rows.reverse()                              # worst→best
        return [r['team_id'] for r in rows]

    non_playoff      = [r['team_id'] for r in standings.values() if r['team_id'] not in playoff_team_ids]
    divisional_out   = [tid for tid, w in eliminated_in.items() if w == PLAYOFF_DIVISIONAL]
    conf_out         = [tid for tid, w in eliminated_in.items() if w == PLAYOFF_CONF_CHAMP]
    runner_up        = [tid for tid, w in eliminated_in.items() if w == PLAYOFF_LEAGUE_CHAMP]

    return (
        _sort_worst_first(non_playoff)
        + _sort_worst_first(divisional_out)
        + _sort_worst_first(conf_out)
        + _sort_worst_first(runner_up)
        + ([champion_id] if champion_id else [])
    )


async def generate_annual_draft_class(db: AsyncSession, league_id: uuid.UUID) -> None:
    """
    Generate the draft class for the upcoming draft. Called immediately when a
    season ends so coaches have the full offseason window to scout and set boards.
    League stays in 'offseason' status — the cron advances to the actual draft run.
    """
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    last_season = result.scalar_one()

    order     = await _draft_order_from_standings(db, league_id)
    order_str = [str(tid) for tid in order]

    positions = list(ROSTER_SLOTS.keys())
    weights   = [ROSTER_SLOTS[p] for p in positions]
    for _ in range(DRAFT_CLASS_SIZE):
        pos = random.choices(positions, weights=weights)[0]
        age = random.choice(DRAFT_CLASS_AGES)
        p   = generate_player(pos, age=age)
        db.add(Player(
            league_id=league_id,
            team_id=None,
            name=p['name'],
            position=p['position'],
            age=p['age'],
            stats=p['stats'],
            composite=p['composite'],
            potential=p['potential'],
            is_draft_eligible=True,
        ))

    last_season.draft_state = {
        'rounds':      DRAFT_ROUNDS,
        'total_picks': DRAFT_ROUNDS * len(order),
        'order':       order_str,
        'picks':       [],
    }

    # Clear per-coach player rankings — prior class IDs are invalid for the new class
    result = await db.execute(select(Team).where(Team.league_id == league_id))
    from sqlalchemy.orm.attributes import flag_modified
    for team in result.scalars().all():
        if team.draft_board:
            team.draft_board = {
                'position_priority': team.draft_board.get('position_priority', [None] * 5),
                'player_ranking': [],
            }
            flag_modified(team, 'draft_board')

    await db.commit()


def _cpu_draft_pick(available: list, roster_counts: dict[str, int]) -> 'Player | None':
    """Pick best available for a CPU team using urgency scoring."""
    if not available:
        return None

    def urgency(pos: str) -> float:
        deficit = max(0, ROSTER_SLOTS[pos] - roster_counts.get(pos, 0))
        if deficit <= 0:
            return -1.0
        return PICK_PRIORITY.get(pos, 1) * (deficit / ROSTER_SLOTS[pos])

    by_pos: dict[str, list] = defaultdict(list)
    for p in available:
        by_pos[p.position].append(p)

    best_urgency = max(urgency(pos) for pos in by_pos if by_pos[pos])

    if best_urgency > 0:
        # Genuine roster need — pick best at the most urgent position
        best_pos = max(
            (pos for pos in by_pos if by_pos[pos]),
            key=urgency,
        )
        return max(by_pos[best_pos], key=lambda p: p.composite)
    else:
        # Rosters full — pick best available overall regardless of position
        return max(available, key=lambda p: p.composite)


def _board_draft_pick(
    available: list,
    position_priority: list[str | None],
    positions_filled: set[str],
    player_ranking: list[str] | None = None,
) -> tuple['Player | None', str | None]:
    """
    Pick using the coach's draft board.

    Walks the priority list (skipping already-filled positions) and picks the
    best available at the first position within DRAFT_TOLERANCE of the overall
    best player. Falls back to overall best if no priority position qualifies.

    If player_ranking is provided (list of player ID strings), it is used to
    determine preference order instead of composite. Unranked players fall back
    to composite ordering.

    Returns (player, priority_position_used_or_None).
    """
    if not available:
        return None, None

    if player_ranking:
        rank_index = {pid: i for i, pid in enumerate(player_ranking)}

        def rank_key(p):
            pid = str(p.id)
            return (0, rank_index[pid]) if pid in rank_index else (1, -p.composite)
    else:
        def rank_key(p):
            return (0, -p.composite)

    best_overall = min(available, key=rank_key)

    by_pos: dict[str, list] = defaultdict(list)
    for p in available:
        by_pos[p.position].append(p)

    active_priority = [pos for pos in position_priority if pos and pos not in positions_filled]

    for pos in active_priority:
        candidates = by_pos.get(pos, [])
        if not candidates:
            continue
        best_at_pos = min(candidates, key=rank_key)
        if best_overall.composite - best_at_pos.composite <= DRAFT_TOLERANCE:
            return best_at_pos, pos

    return best_overall, None  # no priority position within tolerance


async def run_full_draft(db: AsyncSession, league_id: uuid.UUID) -> None:
    """
    Execute all draft picks for a league using each team's board (human teams)
    or urgency algorithm (CPU teams). Called by the cron after the offseason window.
    Stores the full pick log in season.draft_state and moves the league to preseason.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from sim.player_gen import assign_draft_label

    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one()
    state  = dict(season.draft_state)

    # If picks were already committed in a prior run, skip straight to finalization
    if state.get('picks'):
        await _finalize_draft(db, league_id)
        return

    order  = [uuid.UUID(tid) for tid in state['order']]
    n      = len(order)

    result = await db.execute(select(Team).where(Team.league_id == league_id))
    teams  = {t.id: t for t in result.scalars().all()}
    team_names = {t.id: t.name for t in teams.values()}

    # Per-team tracking
    roster_counts:     dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    positions_filled:  dict[uuid.UUID, set[str]]       = defaultdict(set)

    # Pre-load existing roster counts
    result = await db.execute(
        select(Player).where(Player.league_id == league_id, Player.team_id != None)
    )
    for p in result.scalars().all():
        roster_counts[p.team_id][p.position] += 1

    picks = []
    for pick_num in range(state['total_picks']):
        team_id   = order[pick_num % n]
        round_num = pick_num // n + 1

        # Load remaining draft class
        result = await db.execute(
            select(Player).where(
                Player.league_id == league_id,
                Player.is_draft_eligible == True,
            )
        )
        available = list(result.scalars().all())
        if not available:
            break

        team = teams[team_id]
        if team.coach_id is not None:
            # Human team — use draft board
            board          = team.draft_board or {}
            priority       = board.get('position_priority', [])
            player_ranking = board.get('player_ranking', [])
            player, pos_used = _board_draft_pick(available, priority, positions_filled[team_id], player_ranking)
            if pos_used:
                positions_filled[team_id].add(pos_used)
        else:
            # CPU team — urgency algorithm
            player = _cpu_draft_pick(available, roster_counts[team_id])

        if player is None:
            break

        player.team_id           = team_id
        player.is_draft_eligible = False
        roster_counts[team_id][player.position] += 1

        picks.append({
            'pick':            pick_num + 1,
            'round':           round_num,
            'team_id':         str(team_id),
            'team_name':       team_names[team_id],
            'player_id':       str(player.id),
            'player_name':     player.name,
            'position':        player.position,
            'age':             player.age,
            'composite_label': assign_draft_label(player.composite),
        })

    state['picks'] = picks
    season.draft_state = state
    flag_modified(season, 'draft_state')
    await db.commit()

    await _finalize_draft(db, league_id)


async def _finalize_draft(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Clear draft eligibility, cull FA pool, move league to preseason."""
    result = await db.execute(
        select(Player).where(Player.league_id == league_id, Player.is_draft_eligible == True)
    )
    for p in result.scalars().all():
        p.is_draft_eligible = False

    for pos, cap in FA_MAX_PER_POSITION.items():
        result = await db.execute(
            select(Player)
            .where(
                Player.league_id == league_id,
                Player.team_id.is_(None),
                Player.position  == pos,
                Player.retired   == False,  # noqa: E712
            )
            .order_by(Player.composite.desc())
        )
        for excess in result.scalars().all()[cap:]:
            await db.execute(
                delete(PlayerGameStats).where(PlayerGameStats.player_id == excess.id)
            )
            await db.delete(excess)

    result = await db.execute(select(League).where(League.id == league_id))
    league = result.scalar_one()
    league.status = LeagueStatus.preseason
    await db.commit()


async def start_preseason(db: AsyncSession, league_id: uuid.UUID) -> None:
    """Alias — league is already in preseason after draft finalization."""
    pass


async def end_preseason(db: AsyncSession, league_id: uuid.UUID) -> None:
    """After the preseason window, run CPU roster cleanup then start the regular season."""
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one()
    await run_cpu_roster_moves(db, season)
    await db.commit()
    await start_new_season(db, league_id)


async def get_draft_class(db: AsyncSession, league_id: uuid.UUID) -> list[dict]:
    """Return all draft-eligible players in scout (draft-label) view."""
    from sim.player_gen import assign_draft_label, POSITION_STATS

    result = await db.execute(
        select(Player)
        .where(Player.league_id == league_id, Player.is_draft_eligible == True)
        .order_by(Player.composite.desc())
    )
    out = []
    for p in result.scalars().all():
        stat_names = POSITION_STATS[p.position]
        out.append({
            'id':        str(p.id),
            'name':      p.name,
            'position':  p.position,
            'age':       p.age,
            'composite': assign_draft_label(p.composite),
            'stats':     {n: assign_draft_label(v) for n, v in zip(stat_names, p.stats)},
        })
    return out


async def get_draft_results(db: AsyncSession, league_id: uuid.UUID, my_team_id: uuid.UUID) -> dict:
    """Return the full pick log for the most recent draft."""
    result = await db.execute(
        select(Season)
        .where(Season.league_id == league_id)
        .order_by(Season.season_number.desc())
        .limit(1)
    )
    season = result.scalar_one_or_none()
    if not season or not season.draft_state:
        return {'picks': [], 'my_picks': []}

    picks    = season.draft_state.get('picks', [])
    my_picks = [p for p in picks if p.get('team_id') == str(my_team_id)]
    return {'picks': picks, 'my_picks': my_picks, 'rounds': season.draft_state.get('rounds', DRAFT_ROUNDS)}
