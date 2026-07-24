# Training & Draft Potential — Implementation Plan

> **RESUME / STATUS (2026-07-15):** Both phases now **code-complete, not yet committed.**
> - **Phase 1** (training loop): committed — `0d2f2bf` (backend) + `8ec66b6` (frontend); migration
>   `d7f4a1b9c2e3` applied as SQL in Railway.
> - **Phase 2** (potential surfacing): implemented this session, uncommitted. No schema change.
>   - §6 `assign_ceiling_label(composite, potential, player_id)` in `backend/sim/player_gen.py`
>     (fuzzy tier delta + per-player jitter `CEILING_JITTER=3.0`); tests in
>     `backend/tests/test_ceiling_label.py` (dependency-free, green).
>   - §7 `ceiling_label` on `PlayerScoutItem` / `PlayerRosterItem` / `DraftPlayerItem`; populated in
>     `_to_scout_items` + `get_roster` (`routers/leagues.py`) and `get_draft_class` (`services/league_service.py`).
>   - §8 CPU draft blend: `_cpu_draft_value` + potential-weighted picks in `_cpu_draft_pick`
>     (`k=DRAFT_POTENTIAL_WEIGHT 0.35`, per-team `DRAFT_PHILOSOPHY_JITTER 0.15`, age-discounted to
>     `DRAFT_MATURITY_AGE 26`). **Deliberately scoped to CPU only** — `_board_draft_pick` runs only for
>     human teams, so it was left untouched (blending into it would override a human's stated board).
>     Confirmed `run_cpu_roster_moves` signs FAs by `composite.desc()`, so cut young projects stay in the
>     pool → "given-up-on gem" mechanic works, no change needed.
>   - §9 Flutter: shared `app/lib/widgets/upside.dart` (`UpsideChip`) wired into scout, roster, draft screens.
> **Next:** commit Phase 1 is already in; commit Phase 2, deploy, playtest. `flutter analyze` clean on changed files.

## Goal / why

Adds two linked features that turn the game from "set roster, wait" into an
active management loop with a multi-season arc:

- **Training** — spend limited points between games to develop players, at a
  risk/reward cost (upgrade vs. injury vs. "lost confidence" decline). Fills the
  "spectator during the wait" gap and is where a human's edge over the CPU shows.
- **Draft/FA potential** — surface each player's hidden ceiling as a *fuzzy*
  upside grade, so drafting/scouting becomes a boom-or-bust decision (finished
  product vs. raw project) instead of "take the highest current rating."

They are **one loop**: draft for ceiling → develop via training → reap a star.
Potential you can't realize is flavor text; training is what gives it teeth.

Key existing hooks discovered:
- `Player.potential` already exists, generated at `sim/player_gen.py` with the
  comment *"theoretical peak (for v3 progression system)"* — this was designed for.
- `apply_aging` (`backend/app/services/league_service.py:704`) is the canonical
  pattern for mutating `stats` + recomputing `composite`; training mirrors it.
- The sim already treats human/CPU teams identically via `team.coach_id`.

---

## Locked design decisions

| # | Decision |
|---|----------|
| 1 | A **cycle = one game week**. Training happens between weeks. |
| 2 | Cycle points are **use-it-or-lose-it** — no rollover. |
| 3 | **Per-session risk resolution** — dumping 9 TP into one player = 3 separate high-intensity sessions = 3 upgrade rolls *and* 3 injury exposures. |
| 4 | The cap is on **sessions per player per season (3)**, not points. Points/cycle (3) is a separate limiter. One session per player per cycle. |
| 5 | `potential` is **fixed at generation** — a player's ceiling is innate. Training realizes it; it never raises it. |
| 6 | A player's true ceiling **stays fuzzy forever**, even once owned. The "blossom" reveals through results. Potential appears on the **FA board** too (given-up-on gems). |
| 7 | Training runs in the **regular season only** (playoff rosters are set). |
| 8 | Upside grade is a **subtle, honest hint** (small jitter, rarely off by a tier). The real boom/bust risk lives in the *development RNG*, not in a deceptive grade. One knob — dial jitter up later if the draft feels "solved." |
| 9 | Exact `potential` is **never shown anywhere** — always a fuzzy tier grade. Unifying principle: *you never really know a guy's ceiling until you coach him up.* |
| 10 | **Age-gated attainable ceiling.** Training targets an age-gated soft ceiling, not raw potential — full potential only unlocks at `DEV_MATURITY_AGE` (26). With decline starting at 29 (existing curve), that gives a **26–28 window** to realize potential: aggressive training → ~26 (more injury risk), patient → ~28. No capping a roster at 23. **Untrained players plateau *below* potential** (natural aging tops out on the 25–28 flat curve); potential is unlocked only by training. `apply_aging` is also capped at `potential` so natural growth never overshoots. |

Two orthogonal limiters, doing different jobs:
- **Points/cycle (3)** — caps burst within a window; forces choosing who gets attention now.
- **Sessions/player/season (3)** — caps total investment in one guy; forces spreading across the roster over time. Fully developing a player takes ≥ 3 cycles = a season-long commitment.

---

## Design constants (all tunable)

```python
TRAIN_POINTS_PER_CYCLE    = 3    # per team, per week, use-it-or-lose-it
TRAIN_SESSIONS_PER_PLAYER = 3    # per season, reset at rollover
# intensity = points spent in a single session (1–3)
```

---

## Schema deltas (one Alembic migration)

- `Team.train_points: int` — default 3, current cycle's budget.
- `Player.train_sessions_used: int` — default 0, reset each season.
- `Player.trained_in_week: int` — default 0. The season week a player was last
  trained; if it equals `season.current_week`, this cycle's session is spent.
  Enforces *one session/player/cycle* with no extra table.

---

## Phase 1 — Training core (ships solo value first)

### 1. `sim/training_sim.py` (new — pure, unit-tested, mirrors `injury_sim.py`)

One resolution function shared by humans and CPU:

```
resolve_training_session(stats, composite, potential, position, age, intensity) -> result
```

Per-session resolution (decision #3 — each session its own roll; decision #10 — age-gated ceiling):

```python
ceiling         = potential - max(0, 26 - age) * 1.25  # DEV_MATURITY_AGE=26, DEV_GAP_PER_YEAR=1.25
headroom        = max(0, ceiling - composite)
headroom_factor = min(1.0, headroom / 10)          # gains dry up near ceiling
age_factor      = 1 + max(0, (age - 27) * 0.08)    # older = more fragile

injury_p  = 0.03 * intensity * age_factor
upgrade_p = 0.18 * intensity * headroom_factor
decline_p = 0.07 + 0.05 * (1 - headroom_factor)    # "lost confidence", worse near ceiling
```

Resolve sequentially:
1. `rand < injury_p` → **injury** via the existing injury system, multi-week only,
   **never career-ending** (`injury_games_remaining` = 1–4). Training aborts, no gain.
2. else `rand < upgrade_p` → **upgrade**: spread the gain across **3–4
   weighted-random attributes** (weighted toward the position's important stats,
   never revealing which), +1–3 each scaled by intensity — a "developed this week"
   feel. Recompute composite (`WEIGHTS_6` / `WEIGHTS_3`). **Clamp so composite
   never exceeds the age-gated `ceiling`** — the hard cap that prevents super-teams
   and early-career maxing (decision #10).
3. else `rand < upgrade_p + decline_p` → **decline**: −1 to −2 on a random stat,
   recompute, floor 30.
4. else → no change.

Bumping a *weighted-random* stat (not a player-chosen one) preserves the
hidden-weighting design — training can't be used to reverse-engineer engine values.

### 2. Endpoint `POST /{league_id}/teams/{team_id}/train`

Body `{player_id, points}`. Validates:
- team owned by caller
- `points <= team.train_points`
- `player.team_id == team_id`
- `train_sessions_used < 3`
- `trained_in_week != current_week`

On success: call resolver; persist mutated `stats` / `composite` / injury
(reassign `player.stats = [...]` like `apply_aging` does for JSONB);
`train_sessions_used += 1`; `trained_in_week = current_week`;
`team.train_points -= points`. Return the outcome (upgrade / decline / injury /
none) so the UI can show flavor ("struggled in a drill — lost confidence").

### 3. Cron hooks in `_advance_regular_week` (`league_service.py:566`)

- **After** `season.current_week += 1` (new cycle opens): reset every team's
  `train_points = 3` (use-it-or-lose-it — just overwrite).
- Call `run_cpu_training(db, season)` (see §4) so CPUs spend before their next game.
- **Season rollover reset**: add `player.train_sessions_used = 0` to the existing
  `apply_aging` loop (`league_service.py:714`) — it already iterates every player.

### 4. `run_cpu_training(db, season)`

Per CPU team, target score `headroom · rotation_weight · youth`; spend the cycle's
points on top young high-headroom rotation players at **moderate intensity (1–2)**
so CPUs don't injure their own roster into the ground. Uses the shared resolver and
respects the same caps. Aggressiveness can later become a per-team difficulty trait.

### 5. Flutter training screen

Roster list showing each player's remaining sessions + fuzzy upside. Tapping a
player shows the intensity choice (1–3 points) with risk/reward stated explicitly
("higher intensity → better upgrade odds, higher injury risk"). Surface cycle
points remaining. Optional (on-brand) push notification on a training injury via
existing `fcm_token` infra.

---

## Phase 2 — Draft/FA potential surfacing

### 6. Upside grade helper (fuzzy, never numeric) — in `player_gen.py`

Express upside as a **tier delta**, not a number. Compare `assign_label(potential)`
rank vs `assign_label(composite)` rank, plus a **small per-player deterministic
jitter** (seed on `player.id` so it's stable across refreshes):

```
High Upside   → ceiling ≥ 2 tiers above current
Some Upside    → 1 tier above
Near Ceiling   → same tier (finished product)
```

Per decision #8: keep jitter **subtle** — the grade should be trustworthy; the real
uncertainty lives in the development RNG (upgrade/decline/injury + hidden variance
in how fast a player closes headroom), so two "High Upside" players can still pan out
differently. Never show the number (decision #9), even when owned; the blossom
reveals through results.

### 7. Add `ceiling_label` to schemas + endpoints

- `PlayerScoutItem` (`schemas.py:131`) → feeds **free-agents** (`leagues.py:301`)
  and **scout_team** (`leagues.py:292`). ✅ FA board gets upside (decision #6).
- `DraftPlayerItem` (`schemas.py:339`) → **draft board** (`league_service.py:1133`).
- `PlayerRosterItem` (`schemas.py:141`) → owned roster shows the same fuzzy grade
  (not the number).

### 8. CPU draft blend — `_cpu_draft_pick` (`league_service.py:967`) & `_board_draft_pick` (~997)

```
eval = composite + k · (potential - composite) · age_factor    # k ≈ 0.35
```

Plus a small **per-team philosophy jitter** so all 31 CPUs don't draft identically —
that irrationality leaves board value for the human to find. Because CPU
*active-roster* logic still favors current ability, young projects naturally get cut
into the FA pool → the "given-up-on gem" mechanic emerges for free. **When building,
confirm `run_cpu_roster_moves` doesn't accidentally shield them.**

### 9. Flutter: upside grade on draft board, FA board, and roster.

---

## Sequencing & verification

1. Migration (schema deltas)
2. `sim/training_sim.py` + unit tests — the math is the risky part: test headroom
   gating, ceiling clamp, age injury scaling, per-session independence
3. Endpoint + roster/league schema additions
4. Cron hooks (replenish points, reset sessions, one-session/cycle guard)
5. `run_cpu_training`
6. Flutter training UI
7. Upside grade helper
8. `ceiling_label` on scout / draft / roster schemas + endpoints
9. CPU draft blend
10. Flutter upside grade display

**End-to-end check:** advance a league several cycles and confirm — points refresh
each week, session cap holds, one-session-per-cycle holds, composite never crosses
potential, CPUs develop their youth, sessions reset at season rollover, and the FA
pool accumulates undervalued young players.

---

## Tuned values (rebalanced 2026-07-24 — "moderate" impact pass)

First pass felt too weak in playtest: ~1–2 upgrades a season and 2 injuries. Root
cause was the age gate — a young player's attainable ceiling sat only a couple pts
above his composite, so successful rolls clamped to "none." Rebalanced to make an
upgrade the common outcome while keeping the multi-season arc (values in `sim/training_sim.py`
unless noted):
- `BASE_UPGRADE = 0.28` (was 0.20), `BASE_INJURY = 0.025` (was 0.03), `DECLINE_BASE = 0.04` (was 0.07)
- `HEADROOM_FULL = 7.0` (was 10) — gains stay un-throttled with less headroom
- `DEV_GAP_PER_YEAR = 0.75` (was 1.25) — young players get real headroom now (22yo ceiling ≈ potential−3, was −5)
- `TRAIN_SESSIONS_PER_PLAYER = 4` (was 3, in `league_service.py`) — watch one guy actually grow
- Unchanged: `DEV_MATURITY_AGE = 26`, upgrade spreads across `3..4` attributes (+1–3 each ×intensity),
  `CPU_MAX_INTENSITY = 2`
- Measured @ intensity 3 / full headroom: ~78% upgrade, ~4% decline, ~7.5% injury.

### Injury persistence fix (2026-07-24)
Training injuries now set `player.on_ir = True` (endpoint + `_cpu_train_team`), mirroring the
game-injury path in `sim_bridge.write_back_injuries`. Previously only `injury_games_remaining`
was set, so the injured player still occupied his active slot and no FA replacement could be
signed. Now the slot frees, sign an FA, activate off IR on recovery — identical to a game injury.

### Draft board reset (2026-07-24)
`generate_annual_draft_class` now resets `position_priority` to `[None]*5` each offseason (it
already cleared `player_ranking`); prior-season priorities no longer carry over.

**Measured pace** (full headroom): int1 ~0.6, int2 ~1.5, int3 ~2.7 composite/season.
**Career arc** (high-ceiling prospect, ~16 headroom, drafted at 22):
- Aggressive (int3): +3–4/season early → ~95–96% of potential by 26–27
- Patient (int1): ~90% by ~28
- Untrained: plateaus ~86%, potential never unlocked, declines at 29

## Tuning knobs (revisit after playtest)

- `BASE_UPGRADE` / `BASE_INJURY` / `DECLINE_BASE` — core risk/reward feel.
- Per-upgrade magnitude: `UPGRADE_STATS_MIN..MAX` + per-stat bump, and `HEADROOM_FULL` (10).
- `DEV_GAP_PER_YEAR` / `DEV_MATURITY_AGE` — how hard the age gate bites.
- Upside-grade jitter magnitude (decision #8 — start subtle).
- CPU training aggressiveness and draft blend weight `k`.
- Points/cycle and sessions/player if the pacing feels off.
