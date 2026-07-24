"""
Dependency-free tests for sim.training_sim (no pytest needed).

Run from backend/:   python tests/test_training_sim.py
Exits non-zero on failure.
"""
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sim.training_sim import (  # noqa: E402
    resolve_training_session,
    attainable_ceiling,
    _composite,
    _weights_for,
    DEV_MATURITY_AGE,
    DEV_GAP_PER_YEAR,
    STAT_CEIL,
    STAT_FLOOR,
)
from sim.player_gen import POSITION_STATS  # noqa: E402

_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok:   {msg}")


def stats_for(position, base):
    return [base] * len(POSITION_STATS[position])


# ── 1. composite never exceeds potential, ever ───────────────────────────────
def test_ceiling_never_exceeded():
    rng = random.Random(1)
    position = 'QB'
    breaches = 0
    for _ in range(5000):
        stats = stats_for(position, 60)
        comp  = _composite(stats, _weights_for(position))
        potential = comp + rng.uniform(0, 12)   # varied headroom incl. below-ceiling starts
        ceiling = attainable_ceiling(24, potential)
        res = resolve_training_session(stats, comp, potential, position, 24, 3, rng)
        # Training must never raise composite past the age-gated ceiling.
        if res.composite > max(comp, ceiling) + 1e-9:
            breaches += 1
    check(breaches == 0, f"training never raised composite past the age-gated ceiling across 5000 sessions ({breaches} breaches)")


# ── 1b. age gate plateaus young players below potential; opens at maturity ────
def test_age_gate_plateau():
    rng = random.Random(42)
    position  = 'CB'
    potential = 88
    for age in (22, 24, DEV_MATURITY_AGE):
        expected_gap = max(0, DEV_MATURITY_AGE - age) * DEV_GAP_PER_YEAR
        stats = stats_for(position, 60)
        comp  = _composite(stats, _weights_for(position))
        # Train heavily for many sessions, feeding the result back (a "career").
        for _ in range(600):
            res = resolve_training_session(stats, comp, potential, position, age, 3, rng)
            if res.outcome in ('upgrade', 'decline'):
                stats, comp = res.stats, res.composite
        ceiling = attainable_ceiling(age, potential)
        check(abs(ceiling - (potential - expected_gap)) < 1e-9,
              f"age {age}: ceiling {ceiling} == potential-{expected_gap}")
        check(comp <= ceiling + 1e-9,
              f"age {age}: trained comp {comp} never passed ceiling {ceiling}")
        check(comp >= ceiling - 3,
              f"age {age}: heavy training reached the ceiling (comp {comp} near {ceiling})")
        if expected_gap > 0:
            check(comp < potential - 0.5,
                  f"age {age}: young player capped below potential ({comp} < {potential})")


# ── 2. a player at his ceiling cannot upgrade ────────────────────────────────
def test_no_gain_at_ceiling():
    rng = random.Random(2)
    position = 'WR'
    stats = stats_for(position, 70)
    comp  = _composite(stats, _weights_for(position))
    upgrades = 0
    for _ in range(3000):
        res = resolve_training_session(stats, comp, comp, position, 23, 3, rng)  # potential == composite
        if res.outcome == 'upgrade':
            upgrades += 1
    check(upgrades == 0, f"at-ceiling player got {upgrades} upgrades (expected 0)")


# ── 3. high headroom produces meaningful upgrade rate ────────────────────────
def test_upgrades_happen_with_headroom():
    rng = random.Random(3)
    position = 'RB'
    stats = stats_for(position, 60)
    comp  = _composite(stats, _weights_for(position))
    counts = {'upgrade': 0, 'decline': 0, 'injury': 0, 'none': 0}
    N = 5000
    for _ in range(N):
        res = resolve_training_session(stats, comp, comp + 20, position, 23, 3, rng)
        counts[res.outcome] += 1
    rate = counts['upgrade'] / N
    # intensity 3, full headroom → ~0.78 upgrade rate:
    #   upgrade_p = BASE_UPGRADE 0.28 × 3 = 0.84, less the 0.075 injury pre-empt.
    check(0.72 < rate < 0.84, f"upgrade rate {rate:.2f} in expected band (~0.78)")
    print(f"  distribution @ intensity 3, full headroom: {counts}")


# ── 4. older players are injured more often ──────────────────────────────────
def test_age_raises_injury():
    def injury_rate(age, seed):
        rng = random.Random(seed)
        position = 'DE'
        stats = stats_for(position, 65)
        comp  = _composite(stats, _weights_for(position))
        inj = sum(
            resolve_training_session(stats, comp, comp + 15, position, age, 3, rng).outcome == 'injury'
            for _ in range(6000)
        )
        return inj / 6000
    young = injury_rate(22, 10)
    old   = injury_rate(36, 11)
    check(old > young, f"older injury rate {old:.3f} > younger {young:.3f}")


# ── 5. intensity raises both upgrade and injury odds ─────────────────────────
def test_intensity_scales():
    def rates(intensity, seed):
        rng = random.Random(seed)
        position = 'LB'
        stats = stats_for(position, 62)
        comp  = _composite(stats, _weights_for(position))
        up = inj = 0
        N = 6000
        for _ in range(N):
            res = resolve_training_session(stats, comp, comp + 20, position, 25, intensity, rng)
            up  += res.outcome == 'upgrade'
            inj += res.outcome == 'injury'
        return up / N, inj / N
    up1, inj1 = rates(1, 20)
    up3, inj3 = rates(3, 21)
    check(up3 > up1, f"upgrade rate rises with intensity ({up1:.2f} -> {up3:.2f})")
    check(inj3 > inj1, f"injury rate rises with intensity ({inj1:.3f} -> {inj3:.3f})")


# ── 6. stats stay within [30, 95] and injuries are multi-week, bounded ───────
def test_bounds():
    rng = random.Random(6)
    for position in POSITION_STATS:
        stats = stats_for(position, 94)          # near ceiling
        comp  = _composite(stats, _weights_for(position))
        for _ in range(500):
            res = resolve_training_session(stats, comp, 99, position, 30, 3, rng)
            check_ok = all(STAT_FLOOR <= s <= STAT_CEIL for s in res.stats)
            if not check_ok:
                _failures.append(f"{position} stat out of bounds: {res.stats}")
            if res.outcome == 'injury' and not (1 <= res.injury_games <= 4):
                _failures.append(f"injury_games {res.injury_games} out of [1,4]")
    check(not any('out of bounds' in f or 'injury_games' in f for f in _failures),
          "all stats within [30,95], injuries within [1,4] weeks")


if __name__ == '__main__':
    for t in (
        test_ceiling_never_exceeded,
        test_age_gate_plateau,
        test_no_gain_at_ceiling,
        test_upgrades_happen_with_headroom,
        test_age_raises_injury,
        test_intensity_scales,
        test_bounds,
    ):
        print(f"\n{t.__name__}:")
        t()

    print("\n" + "=" * 50)
    if _failures:
        print(f"{len(_failures)} FAILURE(S):")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL TESTS PASSED")
