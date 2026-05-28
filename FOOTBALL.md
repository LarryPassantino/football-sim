# Gridiron Empire — Design Document

*Last updated: May 2026. Backend + cron fully deployed on Railway; per-game stats complete; standings endpoint next.*

---

## Concept

A mobile-first American football team management simulator. Draft a roster from a generated player pool, sim through a full season one game at a time, and manage your roster between games. Players age and develop across seasons. The league is persistent and living — CPU manages teams when humans aren't present, and new players can take over a CPU team and join the competition.

---

## Market Position

- **Football Manager** and its clones dominate soccer — no comparable product exists for American football
- **Madden franchise mode** is buried in a $70 console game with no standalone mobile equivalent
- **Fantasy football** proves the appetite for NFL roster optimization is massive — this goes further and lets you actually run the team
- **Deep Route** (now obscure predecessor) had a small but intensely engaged user base despite minimal polish — players treated reverse-engineering the sim engine as a meta-game. This is the target audience.

---

## League Structure

- **16 teams** per league: 2 conferences × 2 divisions × 4 teams
- **Fictional league** — no NFL licensing (EA holds NFL rights; fictional branding avoids the issue and allows deliberate tuning)
- **One game per day** — daily engagement loop, roster moves between games
- **17-game regular season** (NFL-style) followed by a 3-round playoff
- CPU auto-manages all teams without a human coach
- When a human joins a league, they take over a CPU team and inherit its current roster and history
- Multiple leagues can run simultaneously (see Monetization)

---

## Roster Structure

34 players per team. No FB position (scrapped — power back role filled by high-BLOCK/STR RB).

| Group | Starters | Backup | Total |
|---|---|---|---|
| QB | 1 | 1 | 2 |
| WR | 3 (2 outside + slot) | 1 | 4 |
| TE | 1 | 1 | 2 |
| RB | 1 | 1 | 2 |
| OL | 5 (one group) | 1 | 6 |
| DT | 2 | 1 | 3 |
| DE | 2 | 1 | 3 |
| LB | 3 | 1 | 4 |
| CB | 2 | 1 | 3 |
| S | 2 | 1 | 3 |
| K | 1 | — | 1 |
| P | 1 | — | 1 |
| **Total** | | | **34** |

**KR** is a role, not a roster slot. Any WR, RB, or CB can be assigned as returner; their SPEED, AGILITY, STRENGTH, STAMINA stats determine KR effectiveness.

---

## Position Stats

Each position has a primary **SKILL** stat and 5 supporting stats, in priority order. The SKILL stat carries the most weight but a lopsided player (high skill, low everything else) underperforms a well-rounded one. K and P use 3 stats only.

| Position | SKILL | Stat 2 | Stat 3 | Stat 4 | Stat 5 | Stat 6 |
|---|---|---|---|---|---|---|
| QB | PASSING | AWARENESS | ARM | AGILITY | SPEED | STAMINA |
| RB | BREAK TACKLE | STRENGTH | CATCHING | SPEED | STAMINA | AGILITY |
| TE | CATCHING | BLOCK | STRENGTH | STAMINA | SPEED | AGILITY |
| WR | CATCHING | SPEED | ROUTE | AGILITY | STAMINA | STRENGTH |
| OL | BLOCK | STRENGTH | AWARENESS | AGILITY | STAMINA | SPEED |
| DT | DISRUPT | STRENGTH | TACKLE | STAMINA | AGILITY | SPEED |
| DE | PRESSURE | STRENGTH | AGILITY | SPEED | TACKLE | STAMINA |
| LB | TACKLE | STRENGTH | AGILITY | COVER | STAMINA | SPEED |
| CB | COVER | SPEED | AGILITY | TACKLE | STAMINA | STRENGTH |
| S | COVER | SPEED | TACKLE | AGILITY | STRENGTH | STAMINA |
| K | CLUTCH | ACCURACY | POWER | | | |
| P | PRECISION | POWER | AWARENESS | | | |

**KR stats (from assigned player):** SPEED, AGILITY, STRENGTH, STAMINA

**Fitness score** (used for injury risk): `avg(STRENGTH, AGILITY, STAMINA)` — shared across all positions.

---

## Player Composite & Group Rollup

**Player composite** — weighted sum of stats in priority order:

| Stat rank | 1 (SKILL) | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Weight | 0.30 | 0.22 | 0.18 | 0.14 | 0.10 | 0.06 |

K/P use `[0.50, 0.30, 0.20]`.

**Group composite** — multiple starters averaged, then 80/20 split with backup:
```
group = 0.80 × avg(starter composites) + 0.20 × backup composite
```
All starters play meaningful snaps — the group is only as good as the average across them, not just the best.

---

## The Simulation Engine

### Drive-Based Resolution (two-gate model)

Each drive passes through two gates:

**Gate 1 — Can they move the ball?**
Offense: `OL(45%) + RB(25%) + QB(20%) + WR(10%)`
Defense: `LB(45%) + DT(28%) + S(15%) + DE(12%)`

Outcome: scoring position, punt, or early turnover.

**Gate 2 — Can they finish?**
Offense: `QB(45%) + WR(35%) + RB(10%) + OL(10%)`
Defense: `CB(40%) + DE(22%) + S(20%) + LB(10%) + DT(8%)`

Outcome: touchdown, field goal attempt, or late turnover.

**Hidden insight** players will eventually discover: DT dominates Gate 1 (run stuffing), DE dominates Gate 2 (pass rush). A great DL needs both — they're not interchangeable.

### Game-Day Variance (two-layer modifier)

Applied once per game before drives resolve:
1. **Team-wide factor** (std dev ±5) — shared shift across all units (travel, weather, cohesion)
2. **Per-unit factor** (std dev ±8) — independent variance per position group

The team factor creates correlation (bad days drag everyone down) while unit factors prevent the whole team from going uniformly hot or cold.

### Calibrated outputs (from sim, average vs. average)
- TD rate: ~21% per drive
- Punt rate: ~45%
- Turnover rate: ~14%
- Avg score: ~23 pts/game per team
- Score std dev: ~10 pts (matches real NFL game-to-game variance)

---

## Injuries

Resolved pre-game per starter. Deferred to player/roster layer (requires individual player objects).

- **Risk model:** base injury chance modified by fitness score (avg STR, AGI, STA)
- **Impact:** injured starter replaced by backup — the starter/backup rating gap is the real consequence
- **Cap:** max 2 out-for-game injuries per team per game
- **Season-ending injuries:** player goes to IR, roster spot opens for FA pickup

---

## Player Pool & Draft

### Initial league generation
- ~620 players generated at league creation (544 on rosters + ~75 FA pool)
- **Age distribution is staggered at startup** (roughly 21–33) to prevent mass retirement in a single future season
- FA pool quality clusters in the 55–65 composite range — viable in a pinch, noticeably below drafted starters

### Annual draft class
- ~80–100 new players per season (young, age 21–23) to replace retiring players
- Retiring players leave based on age + decline threshold, freeing FA pool space

### Player progression & decline
- Attribute-based age curves: younger players have higher ceiling, older players decline faster
- Luck factor layered on top: breakout seasons, unexpected decline, injury history
- Attributes influence *rate* of change, not just current value — a high-ceiling young player is a different roster bet than a proven veteran

---

## Season Calendar

One game per day. Full cycle is **24–25 days** per season.

| Phase | Days | Notes |
|---|---|---|
| Regular season | 17 | One game/day |
| Playoffs | 3 | Divisional (week 18) → Conf championships (week 19) → League championship (week 20) |
| Off-season window | 2–3 | New coaches pick a team; everyone preps for the draft |
| Season resolution | 1 | Final standings, awards, stat leaders |
| Draft prep | 1 | Player pool generated, scouting available |
| Draft day | 1 | Snake draft, CPU teams auto-pick |
| Season prep | 1 | Roster finalizing, lineup setting |

Roughly **1.3–1.4 seasons/month** for an active player.

**Off-season window:** The gap between the championship and the next draft. New human coaches joining the league choose an available team during this window (abandoned or expansion slots). Existing coaches use it to scout the incoming draft class. CPU teams hold any unclaimed slots and auto-draft as normal.

## Playoffs

**4 teams per conference qualify** (8 total, 2 conferences).

**Qualification:** Both division winners are guaranteed a spot. The remaining 2 spots per conference go to the next-best records (wild cards).

**Seeding:** Purely by regular season record regardless of division winner status. Tiebreakers: head-to-head → point differential → coin flip.

**Bracket:**
- Week 18 — Divisional round: #1 vs #4, #2 vs #3 (per conference; 4 games total)
- Week 19 — Conference championships: divisional winners face off (2 games)
- Week 20 — League championship: conference champions (1 game)

Higher seed hosts each game.

---

## Season Management

- **One game per day** — daily notification, roster decisions between games
- Roster moves available between games: FA pickups, lineup changes, KR assignment
- When a starter goes to IR, a roster spot opens and the team can sign a FA replacement
- CPU teams auto-manage their own rosters (FA pickups, lineup decisions)

**Mid-season abandonment:** If a human coach quits between games, CPU takes over the team immediately. Roster and history stay intact. Another human can take over the team later. Abandoned teams never become dead weight in the standings — the living league depends on this.

**Mid-season joining discount:** Token price is reduced based on regular season games remaining when a coach joins.

| Games played | Discount |
|---|---|
| 1–8 (first half) | Full price |
| 9–13 (second half) | 50% off |
| 14–17 + playoffs | 75% off |

Discounted availability is a push notification opportunity: "A league near you just hit 50% off."

---

## Monetization

**Core model: free first league, paid access for additional leagues**

Every user gets one league for free — full feature access, no limitations. Additional leagues are paid.

### Access tiers (per additional league)

| Tier | Price (TBD) | Breakeven | Best for |
|---|---|---|---|
| **Token** | ~$1.99/season | — | Trying a second league, casual commitment |
| **Year pass** | ~$9.99/year | ~5 seasons (~4 months) | Regular players not ready to commit long-term |
| **Lifetime pass** | ~$19.99 | ~10 seasons (~7 months) | Hooked players who know they'll stay |

Pricing is illustrative — A/B test at launch.

### End-of-season conversion prompt

At the end of each token-funded season, the player sees three options:
1. **Buy another token** — continue next season
2. **Upgrade to year or lifetime pass** — pass shown at a discount to create urgency
3. **Abandon the team** — leave the league (team reverts to CPU, stays alive in the league)

This is the highest-leverage conversion moment: the player just finished a season, is emotionally invested, and wants to see what happens next. The discounted pass offer at this exact point nudges toward higher-value commitment without being coercive.

### Why the model works
- Zero friction to start — no paywall on the core experience
- Power users (5 leagues at once) self-select into paying more, mirroring fantasy football
- Leagues live forever — a lifetime pass is genuinely compelling because the team and history persist
- Abandonment is a natural churn mechanism: low-engagement coaches exit cleanly, their teams stay healthy under CPU, the league stays alive for everyone else

### Additional revenue
- Optional cosmetics: team name, colors, logo, uniform builder (no gameplay impact)
- Private league creation (invite friends) — potentially token-gated or a premium tier feature

**Data model note:** User → leagues is many-to-many from day one, even if v1 ships with one league per user. Retrofitting multi-league onto a single-league schema is painful.

---

## Phased Scope

| Phase | Scope |
|---|---|
| **v1** | Single league, single season. Draft → sim 17 games → standings. One game/day loop with between-game roster moves. CPU manages other 15 teams. |
| **v2** | Per-game stats, player performance leaders, season history, sim visibility improvements |
| **v3** | Multi-season: aging, retirement, annual draft class, player contracts |
| **v4** | Multi-league: additional leagues via tokens, human takeover of CPU teams |
| **v5** | Private league creation: commissioner creates league, invites friends, live snake draft with auto-pilot fallback |

---

## Stack

- **Mobile:** Flutter (consistent with Cosplanner and other projects)
- **Backend:** Python/FastAPI + PostgreSQL (consistent with other projects)
- **v1 consideration:** Single season could ship with local-only storage (no backend), but multi-league requires accounts and a backend. Design with backend in mind from day one.
- **Sim logic:** Lives in the backend (Python) — never expose weights or formula client-side

---

## Scouting & Stat Visibility

Stats are hidden behind named labels at draft time. Exact numbers are only visible on players you own.

| Label | Range |
|---|---|
| Weak | 30–49 |
| Below Average | 50–62 |
| Average | 63–72 |
| Above Average | 73–82 |
| Elite | 83–95 |

**At draft time:** All stats shown as labels only. "Above Average PASSING" could be a 73 or an 82 — you don't know.

**After drafting:** Exact numbers visible on your own roster immediately. You know what you have; opponents don't.

**Free agents:** Always show labels only — same as draft time.

**Signing a FA:** Exact numbers become visible immediately once they're on your roster.

**Cutting a player:** They return to the FA pool as labels. The engine doesn't track per-coach visibility history — the simplest possible rule. The coach remembers what they had; the game doesn't need to.

This creates a real cut decision: releasing a player surrenders your informational edge on them. You know he was a 78 last season, but in the FA pool he's "Above Average" again. He might have progressed to 84 or declined to 71 — you won't know until you sign him again, and someone else might get there first.

**Trades:** Players you don't own always show labels only. Knowing your own player's exact numbers while the other team sees labels is part of the negotiation dynamic.

**Why this works:**
- Draft feels like scouting, not a spreadsheet — judgment over calculation
- Protects the hidden formula — players can't reverse-engineer composite weights from draft data alone
- Creates genuine uncertainty and boom/bust moments ("I thought he was an 82, he's a 74")
- Feeds the engine-figuring meta — community debate over which label combos are worth drafting
- Engine stays simple — no per-player per-coach visibility tracking needed

---

## Draft System

### League types

| | Admin / Base | Private |
|---|---|---|
| **1st draft** | Automatic snake (CPU-simmed) | Commissioner chooses: automatic snake or live snake |
| **2nd+ draft** | Live, worst→best order | Live, worst→best order |
| **Access** | Open to all | Invite or password |
| **Auto-pilot** | Available for all live drafts | Available for all live drafts |

**Admin-created leagues**
- Mega draft is CPU-simmed at league creation — no human coordination required, teams live immediately
- New players join and choose which CPU team to take over, **first-come-first-served**
- Team selection is the onboarding moment: best record? youngest roster? weakest division? That choice teaches new players what to value
- Players can join mid-season or between seasons
- Living league model: a league running for 3 seasons has teams with real history to inherit

**Private leagues** (v5)
- Commissioner creates the league and invites participants via invite or password
- 1st draft: commissioner chooses automatic snake (CPU-simmed) or live snake
- If live: players claim snake slots **first-come-first-served**, draft runs with per-pick countdown timer

**All live drafts (2nd+ for both league types, optional 1st for private)**
- Coaches participate live or set a **preference queue / watchlist** before the draft
- Auto-pilot fires from the queue when the timer expires — live and auto-pilot coaches coexist seamlessly
- CPU-managed teams auto-pick instantly

### Year 1 — Mega Draft
- **Snake format:** round 1 picks 1→16, round 2 picks 16→1, alternating each round

### Year 2+ — Annual Draft
- **Linear worst→best:** last-place team picks first in every round, champion picks last — no snake reversal
- Draft order = final regular season standings, worst record first
- **Tiebreaker:** 1. head-to-head record, 2. point differential, 3. coin flip
- Worst teams reload fastest; dynasties are structurally discouraged

### Round count
- TBD — needs to cover ~80–100 new players entering the pool each season (age 21–23)
- Undrafted players enter the free agent pool automatically

---

## Build Status

### Sim engine (`backend/sim/`)

Note: `sim/` lives inside `backend/` for Railway deployment — no sys.path hacks needed.

| Module | Status |
|---|---|
| `player_gen.py` — pool generation, fitness scoring | Complete |
| `draft_sim.py` — snake mega-draft, CPU urgency strategy | Complete |
| `football_sim.py` — two-gate drive resolution, game-day variance | Complete |
| `season_sim.py` — full pipeline: pool → draft → schedule → standings → playoffs | Complete |
| `injury_sim.py` — pre-game rolls, fitness-weighted tiers, tick system | Complete |
| `stats_gen.py` — probabilistic per-player stat distribution from drive outcomes | Complete |

### Backend (`backend/`)
| Area | Status |
|---|---|
| FastAPI app + routing | Complete |
| JWT auth (register, login, refresh) | Complete |
| SQLAlchemy async models (League, Coach, Team, Player, Season, Game, PlayerGameStats) | Complete |
| Alembic migrations on Railway Postgres | Complete (3 migrations: initial, add_is_playoff, add_player_game_stats) |
| League creation (draft + schedule) | Complete |
| Regular season advancement (`advance_week`) | Complete |
| Playoff bracket (seeding, 3-round bracket, tiebreakers) | Complete |
| Per-game player stats + game detail endpoint | Complete — `GET /leagues/{id}/games/{game_id}` |
| Matchup endpoint | Complete — `GET /leagues/{id}/games/{game_id}/matchup` |
| Cron job (`advance_games.py`) | Complete — deployed on Railway |
| Railway web service deploy | Complete |
| Standings endpoint | Complete |

### Frontend
| Area | Status |
|---|---|
| Flutter app | Not started — after standings endpoint |

---

## Open Design Questions

- Draft: how many rounds per annual draft? Year 1 human draft position (random vs. chosen)?
- CPU team AI: how smart should auto-management be for roster moves and draft picks?
- Private league creation: token-gated or separate premium tier?
- Team customization: how deep (name only? colors? full uniform builder?)

### Planned features (captured mid-build)

**Team names unique per league**
Team names currently come from the sim engine's hardcoded pool and repeat across leagues. Before multiple leagues are live, the name list should be large enough (or randomized enough) to avoid duplicates, or names should be assigned with per-league uniqueness enforced at creation time.

**Coach-controlled team rename**
A coach should be able to rename their team at any point. Needs a `PATCH /leagues/{id}/teams/{team_id}` endpoint and a rename affordance in the UI. Simple name field on the team home screen.

**Team history view**
Season-by-season record for a team — wins, losses, playoff result, any championships. History is tied to `team_id`, not the team name, so renames don't break it. This slots naturally into v3 (multi-season) but the data model should store season outcomes against `team_id` from the start so history accumulates automatically.

---

## Future Feature: Cross-League Championship (post-v1 idea)

A "Champions League"-style tournament where each season's league champion is pooled into a periodic championship bracket.

**Concept:**
- Every 2–3 months, all league champions from that window are seeded into a single-elimination bracket
- No free agents, no roster moves — each team sims with their current starters as-is
- Pure prestige: best team across all leagues in that period

**Open questions:**
- Window length: 2 months vs. 3 months? Depends on how many leagues are active at launch
- What happens if a champion's team was taken over mid-season? Use the roster at the time of the championship win
- Bracket size: powers of 2 only, so bye weeks if field isn't full
- Separate from the regular season loop entirely — no impact on ongoing leagues
