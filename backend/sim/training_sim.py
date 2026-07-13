"""
training_sim.py — player training resolution (v3 progression system).

Pure, DB-free resolution of a single training session. The API endpoint and the
CPU training routine both call `resolve_training_session`; callers persist the
returned mutation onto the ORM row (mirroring how apply_aging reassigns stats +
composite).

One session = one training action on one player in one cycle. Intensity is the
number of training points spent in that session (1-3): higher intensity raises
both the upgrade chance and the injury chance. Each session is its own roll, so
loading three sessions onto one player over a season is three separate upgrade
rolls AND three separate injury exposures.

Design rules baked in:
  - Gains are gated by headroom (potential - composite): a player at his ceiling
    barely improves, and composite can never exceed `potential`. This is the hard
    cap that prevents runaway super-teams.
  - Older players are more injury-prone.
  - The improved stat is chosen weighted toward the position's important stats,
    but is never surfaced as "the important one" — training can't be used to
    reverse-engineer the engine's hidden weighting.
"""

import random
from dataclasses import dataclass

from .player_gen import POSITION_STATS, WEIGHTS_6, WEIGHTS_3

# ── Tuning knobs (see training_and_potential.md) ─────────────────────────────
BASE_INJURY            = 0.03   # × intensity × age_factor
BASE_UPGRADE           = 0.20   # × intensity × headroom_factor
DECLINE_BASE           = 0.07   # flat "lost confidence" background risk
DECLINE_HEADROOM_BONUS = 0.05   # extra decline risk near the ceiling
HEADROOM_FULL          = 10.0   # headroom (composite pts) at which gains are un-throttled
AGE_FRAGILE_START      = 27     # injury risk starts climbing past this age
AGE_FRAGILE_SLOPE      = 0.08   # per year over AGE_FRAGILE_START
INJURY_WEEKS           = (1, 4) # training injuries are multi-week only, never career-ending
DEV_MATURITY_AGE       = 26     # age at which full potential first becomes attainable
DEV_GAP_PER_YEAR       = 1.25   # composite pts of potential locked per year below maturity
UPGRADE_STATS_MIN      = 3      # a successful session spreads gains across this many …
UPGRADE_STATS_MAX      = 4      # … to this many attributes (weighted toward important ones)
STAT_FLOOR             = 30
STAT_CEIL              = 95


def attainable_ceiling(age: int, potential: float) -> float:
    """
    Age-gated soft ceiling. Below DEV_MATURITY_AGE a slice of potential is locked
    and unlocks with age, so a young player can be developed toward — but never all
    the way to — his potential. Reaches full potential at DEV_MATURITY_AGE (26);
    combined with decline starting at 29, that leaves a 26-28 window to realize it.
    """
    return potential - max(0, DEV_MATURITY_AGE - age) * DEV_GAP_PER_YEAR


@dataclass
class TrainingResult:
    outcome:      str              # 'upgrade' | 'decline' | 'injury' | 'none'
    stats:        list             # new stat list (unchanged for injury/none)
    composite:    float            # new composite (unchanged for injury/none)
    injury_games: int = 0          # games out (only set on 'injury')
    stat_changed: str | None = None  # name of the stat that moved (flavor)
    delta:        int = 0          # +gain on upgrade, -loss on decline, else 0


def _weights_for(position: str):
    return WEIGHTS_3 if position in ('K', 'P') else WEIGHTS_6


def _composite(stats, weights) -> float:
    return round(sum(s * w for s, w in zip(stats, weights)), 1)


def resolve_training_session(
    stats:     list,
    composite: float,
    potential: float,
    position:  str,
    age:       int,
    intensity: int,
    rng:       random.Random = random,
) -> TrainingResult:
    """Resolve one training session. `intensity` is 1-3 (points spent)."""
    intensity = max(1, min(3, intensity))

    # Training targets the age-gated ceiling, not raw potential.
    ceiling         = attainable_ceiling(age, potential)
    headroom        = max(0.0, ceiling - composite)
    headroom_factor = min(1.0, headroom / HEADROOM_FULL)
    age_factor      = 1.0 + max(0, age - AGE_FRAGILE_START) * AGE_FRAGILE_SLOPE

    injury_p  = BASE_INJURY * intensity * age_factor
    upgrade_p = BASE_UPGRADE * intensity * headroom_factor
    decline_p = DECLINE_BASE + DECLINE_HEADROOM_BONUS * (1.0 - headroom_factor)

    # 1) Injury roll is independent and pre-empts any stat change.
    if rng.random() < injury_p:
        return TrainingResult(
            outcome='injury',
            stats=list(stats),
            composite=composite,
            injury_games=rng.randint(*INJURY_WEEKS),
        )

    # 2) Otherwise a single roll splits upgrade / decline / no change.
    r = rng.random()
    if r < upgrade_p:
        return _apply_upgrade(stats, composite, ceiling, position, intensity, rng)
    if r < upgrade_p + decline_p:
        return _apply_decline(stats, composite, position, rng)

    return TrainingResult(outcome='none', stats=list(stats), composite=composite)


def _pick_weighted(idxs, weights, rng) -> int:
    return rng.choices(idxs, weights=[weights[i] for i in idxs])[0]


def _pick_weighted_distinct(idxs, weights, n, rng) -> list:
    """Sample up to n distinct indices, weighted by importance (no replacement)."""
    pool, chosen = list(idxs), []
    for _ in range(min(n, len(pool))):
        i = rng.choices(pool, weights=[weights[j] for j in pool])[0]
        chosen.append(i)
        pool.remove(i)
    return chosen


def _apply_upgrade(stats, composite, ceiling, position, intensity, rng) -> TrainingResult:
    weights = _weights_for(position)
    # Only stats with room to grow are candidates; skew toward important ones.
    candidates = [i for i in range(len(stats)) if stats[i] < STAT_CEIL]
    if not candidates:
        return TrainingResult(outcome='none', stats=list(stats), composite=composite)

    # Spread the gain across a few attributes for a "developed this week" feel.
    n     = rng.randint(UPGRADE_STATS_MIN, UPGRADE_STATS_MAX)
    idxs  = _pick_weighted_distinct(candidates, weights, n, rng)
    new_stats = list(stats)
    for i in idxs:
        new_stats[i] = min(STAT_CEIL, new_stats[i] + min(4, rng.randint(1, intensity + 1)))
    new_comp = _composite(new_stats, weights)

    # Ceiling clamp: shave points off the boosted stats (biggest-weight first)
    # until composite no longer exceeds the age-gated ceiling.
    boosted = sorted(idxs, key=lambda i: weights[i], reverse=True)
    bi = 0
    while new_comp > ceiling and any(new_stats[i] > stats[i] for i in idxs):
        i = boosted[bi % len(boosted)]
        if new_stats[i] > stats[i]:
            new_stats[i] -= 1
            new_comp = _composite(new_stats, weights)
        bi += 1

    if new_comp <= composite:
        # At the ceiling / capped out — no real progress.
        return TrainingResult(outcome='none', stats=list(stats), composite=composite)

    top = max(idxs, key=lambda i: new_stats[i] - stats[i])
    return TrainingResult(
        outcome='upgrade',
        stats=new_stats,
        composite=new_comp,
        stat_changed=POSITION_STATS[position][top],
        delta=sum(new_stats[i] - stats[i] for i in idxs),
    )


def _apply_decline(stats, composite, position, rng) -> TrainingResult:
    weights = _weights_for(position)
    candidates = [i for i in range(len(stats)) if stats[i] > STAT_FLOOR]
    if not candidates:
        return TrainingResult(outcome='none', stats=list(stats), composite=composite)

    idx       = _pick_weighted(candidates, weights, rng)
    loss      = rng.randint(1, 2)
    new_stats = list(stats)
    new_stats[idx] = max(STAT_FLOOR, new_stats[idx] - loss)
    new_comp  = _composite(new_stats, weights)

    if new_comp >= composite:
        return TrainingResult(outcome='none', stats=list(stats), composite=composite)

    return TrainingResult(
        outcome='decline',
        stats=new_stats,
        composite=new_comp,
        stat_changed=POSITION_STATS[position][idx],
        delta=new_stats[idx] - stats[idx],
    )
