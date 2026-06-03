import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from functools import cmp_to_key

from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sim.draft_sim import LEAGUE as LEAGUE_STRUCTURE, build_teams, run_draft
from sim.player_gen import generate_pool
from sim.season_sim import build_schedule

from ..models import (
    Coach, Game, GameStatus, League, LeagueStatus,
    Player, PlayerGameStats, Season, SeasonStatus, Team,
)
from .sim_bridge import clear_all_injuries, play_game
from .push_service import send_game_result

REGULAR_SEASON_WEEKS = 17
OFFSEASON_DAYS       = 4
PLAYOFF_DIVISIONAL   = 18
PLAYOFF_CONF_CHAMP   = 19
PLAYOFF_LEAGUE_CHAMP = 20


# ============================================================
# WEEK ASSIGNMENT
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

    pool      = generate_pool()
    sim_teams = build_teams()
    sim_teams, fa_pool = run_draft(sim_teams, pool, show_rounds=0)

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
                )
                .order_by(Player.composite.desc())
                .limit(1)
            )
            fa = result.scalar_one_or_none()
            if fa:
                fa.team_id = team.id
                fa.on_ir   = False


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
        if coach and coach.fcm_token:
            send_game_result(coach.fcm_token, team.name, my_score, opp_score, opponent)


async def _advance_regular_week(db: AsyncSession, season: Season) -> dict:
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

    await run_cpu_roster_moves(db, season)

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

    await db.commit()
    return {'week_played': season.current_week - 1, 'games': len(games)}


async def _advance_playoff_week(db: AsyncSession, season: Season) -> dict:
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

    await run_cpu_roster_moves(db, season)

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
    league.status = LeagueStatus.offseason
    await db.commit()


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

    sim_teams      = [{'conference': t.conference, 'division': t.division} for t in teams]
    team_idx_to_id = {i: t.id for i, t in enumerate(teams)}

    new_season = Season(
        league_id=league_id,
        season_number=last_season.season_number + 1,
        current_week=1,
    )
    db.add(new_season)
    await db.flush()

    schedule = build_schedule(sim_teams)
    weeks    = _assign_weeks(schedule)

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
