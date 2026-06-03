"""
stats_gen.py — Probabilistic per-player stat distribution from drive outcomes.

The sim resolves drives at the team level. This module takes those outcomes
and distributes stats to individual players weighted by their composite ratings.
Stats are realistic in aggregate but not derived from play-by-play simulation.
"""

import random
from collections import defaultdict


def _distribute(players: list, total: int, power: float = 1.0) -> dict:
    """
    Distribute an integer total among players proportional to composite^power.
    power=1.0 is linear; power=2.0 steepens the curve toward top players.
    Returns {db_id: value}. Rounding error goes to the highest-composite player.
    """
    if not players or total <= 0:
        return {}
    total_comp = sum(p['composite'] ** power for p in players)
    if total_comp == 0:
        share = total // len(players)
        return {p['_db_id']: share for p in players}

    result = {}
    running = 0
    for i, p in enumerate(players):
        if i == len(players) - 1:
            result[p['_db_id']] = max(0, total - running)
        else:
            share = round(total * p['composite'] ** power / total_comp)
            result[p['_db_id']] = share
            running += share
    return result


def _pick(players: list, weights: list = None) -> dict | None:
    """Pick one player by weight (defaults to composite)."""
    if not players:
        return None
    w = weights if weights is not None else [p['composite'] for p in players]
    total = sum(w)
    if total <= 0:
        return random.choice(players)
    r = random.random() * total
    running = 0
    for player, weight in zip(players, w):
        running += weight
        if r <= running:
            return player
    return players[-1]


def generate_game_stats(
    offense_sim: dict,
    defense_sim: dict,
    outcomes: dict,
    run_factor: float = 0.0,
) -> tuple[dict, dict]:
    """
    Probabilistic per-player stat distribution for one team's offensive series
    and the opposing defense against it.

    Returns (off_stats, def_stats) — {player_db_id: {stat_name: int}}.
    Players with all-zero stats are omitted.
    """
    off = defaultdict(lambda: defaultdict(int))
    dfe = defaultdict(lambda: defaultdict(int))

    ro = offense_sim.get('roster', {})
    rd = defense_sim.get('roster', {})

    tds       = outcomes.get('touchdown', 0)
    turnovers = outcomes.get('turnover', 0)

    # Split TDs and turnovers into type — run_factor shifts rush/pass balance
    pass_td_ratio = max(0.35, min(0.85, 0.65 - run_factor * 0.15))
    pass_tds  = round(tds * pass_td_ratio)
    rush_tds  = tds - pass_tds
    ints      = round(turnovers * 0.55)
    fum_lost  = turnovers - ints  # fumbles lost by ball carrier

    # Sacks: shared between OL sacks_allowed and DE/LB sacks
    sack_count = max(0, round(random.gauss(2.5, 1.2)))

    # Net passing yards — run_focus lowers pass base, pass_focus raises it
    raw_pass   = int(random.gauss(270 - run_factor * 30, 55) + (tds - 2.5) * 18 - turnovers * 12)
    pass_yards = max(20, raw_pass - sack_count * 7)

    rush_yards = max(15, int(random.gauss(115 + run_factor * 20, 32)))

    # Receiving yard split: WR 65%, TE 20%, RB 15%
    wr_yards = round(pass_yards * 0.65)
    te_yards = round(pass_yards * 0.20)
    rb_yards = pass_yards - wr_yards - te_yards

    # Rush yard split: RB 82%, QB scrambles 18%
    rb_rush = round(rush_yards * 0.82)
    qb_rush = rush_yards - rb_rush

    # Receptions per group (approximate yards/catch)
    wr_recs = max(0, round(wr_yards / max(1, random.gauss(13, 1.5))))
    te_recs = max(0, round(te_yards / max(1, random.gauss(10, 1.5))))
    rb_recs = max(0, round(rb_yards / max(1, random.gauss(8, 1.0))))
    total_recs = wr_recs + te_recs + rb_recs

    # ==================== OFFENSE ====================

    qbs = ro.get('QB', [])
    wrs = ro.get('WR', [])[:4]
    tes = ro.get('TE', [])[:2]
    rbs = ro.get('RB', [])[:2]
    ols = ro.get('OL', [])

    # QB
    if qbs:
        qb = qbs[0]
        attempts = max(total_recs, round(total_recs / max(0.4, random.gauss(0.63, 0.05))))
        off[qb['_db_id']]['pass_attempts']        = attempts
        off[qb['_db_id']]['pass_completions']     = total_recs
        off[qb['_db_id']]['pass_yards']           = pass_yards
        off[qb['_db_id']]['pass_tds']             = pass_tds
        off[qb['_db_id']]['interceptions_thrown'] = ints
        qb_att = max(1, round(qb_rush / max(1, random.gauss(5, 1))))
        off[qb['_db_id']]['rush_attempts'] = qb_att
        off[qb['_db_id']]['rush_yards']    = qb_rush
        if rush_tds > 0 and random.random() < 0.12:
            off[qb['_db_id']]['rush_tds'] = 1
            rush_tds -= 1

    # WRs — receiving (power=2.0 concentrates yards on the top receiver realistically)
    if wrs:
        for pid, val in _distribute(wrs, wr_yards, power=2.0).items():
            off[pid]['receiving_yards'] += val
        for pid, val in _distribute(wrs, wr_recs, power=2.0).items():
            off[pid]['receptions'] += val

    # TEs — receiving
    if tes:
        for pid, val in _distribute(tes, te_yards).items():
            off[pid]['receiving_yards'] += val
        for pid, val in _distribute(tes, te_recs).items():
            off[pid]['receptions'] += val

    # RBs — rushing + receiving (power=2.0 so starter gets workhorse share)
    if rbs:
        rush_att = max(5, round(rb_rush / max(1, random.gauss(4.2, 0.7))))
        for pid, val in _distribute(rbs, rb_rush, power=2.0).items():
            off[pid]['rush_yards'] += val
        for pid, val in _distribute(rbs, rush_att, power=2.0).items():
            off[pid]['rush_attempts'] += val
        for pid, val in _distribute(rbs, rb_yards, power=2.0).items():
            off[pid]['receiving_yards'] += val
        for pid, val in _distribute(rbs, rb_recs, power=2.0).items():
            off[pid]['receptions'] += val

    # Receiving TDs — WR 65%, TE 20%, RB 15%
    for _ in range(pass_tds):
        r = random.random()
        if r < 0.65 and wrs:
            winner = _pick(wrs)
        elif r < 0.85 and tes:
            winner = _pick(tes)
        elif rbs:
            winner = _pick(rbs)
        else:
            winner = _pick(wrs) if wrs else None
        if winner:
            off[winner['_db_id']]['receiving_tds'] += 1

    # Rush TDs — RBs
    for _ in range(rush_tds):
        winner = _pick(rbs) if rbs else None
        if winner:
            off[winner['_db_id']]['rush_tds'] += 1

    # Fumbles — mostly RBs, some WRs
    fumble_pool = rbs + wrs[:2]
    for _ in range(fum_lost):
        loser = _pick(fumble_pool, weights=[1.0] * len(fumble_pool)) if fumble_pool else None
        if loser:
            off[loser['_db_id']]['fumbles'] += 1
            off[loser['_db_id']]['fumbles_lost'] += 1
            # Not all fumbles result in loss; add a non-lost fumble occasionally
            if random.random() < 0.35:
                off[loser['_db_id']]['fumbles'] += 1  # extra fumble that was recovered

    # OL — sacks allowed (worse OL players allow more; weight inversely by composite)
    if ols and sack_count > 0:
        inv_w = [1.0 / max(1, p['composite'] - 50) for p in ols]
        for _ in range(sack_count):
            loser = _pick(ols, weights=inv_w)
            if loser:
                off[loser['_db_id']]['sacks_allowed'] += 1

    # ==================== DEFENSE ====================

    total_tackles = max(10, int(random.gauss(48, 8)))
    tackle_split = {'LB': 0.38, 'CB': 0.20, 'S': 0.20, 'DT': 0.14, 'DE': 0.08}
    for pos, frac in tackle_split.items():
        players = rd.get(pos, [])
        if players:
            for pid, val in _distribute(players, round(total_tackles * frac)).items():
                dfe[pid]['tackles'] += val

    # Sacks — DE 65%, LB 35%
    des = rd.get('DE', [])
    lbs = rd.get('LB', [])
    for _ in range(round(sack_count * 0.65)):
        w = _pick(des)
        if w:
            dfe[w['_db_id']]['sacks'] += 1
    for _ in range(sack_count - round(sack_count * 0.65)):
        w = _pick(lbs[:2] if lbs else [])
        if w:
            dfe[w['_db_id']]['sacks'] += 1

    # Interceptions — CB 65%, S 35%
    cbs = rd.get('CB', [])
    ss  = rd.get('S', [])
    int_pool    = cbs + ss
    int_weights = [1.5] * len(cbs) + [1.0] * len(ss)
    for _ in range(ints):
        w = _pick(int_pool, weights=int_weights)
        if w:
            dfe[w['_db_id']]['interceptions'] += 1

    # Forced fumbles + recoveries
    ff_pool  = des + lbs
    rec_pool = des + lbs + rd.get('DT', [])
    for _ in range(fum_lost):
        w = _pick(ff_pool)
        if w:
            dfe[w['_db_id']]['forced_fumbles'] += 1
        if random.random() < 0.5:
            w = _pick(rec_pool)
            if w:
                dfe[w['_db_id']]['fumble_recoveries'] += 1

    def _clean(d):
        return {pid: dict(stats) for pid, stats in d.items() if any(v > 0 for v in stats.values())}

    return _clean(off), _clean(dfe)
