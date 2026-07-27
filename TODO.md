# Gridiron Empire — To-Do

## Up Next
- [x] Reduce OFFSEASON_DAYS from 4 to 3 (backend/app/services/league_service.py)
- [x] Team rename — PATCH endpoint + UI on team home screen
- [x] Season 2+ (no draft) — offseason → new season flow; clear old games, generate new schedule, reset week; players keep current rosters
- [x] Draft system — annual draft class; 5 rounds, worst→best linear order; CPU auto-picks; human picks via Draft Room; undrafted go to FA pool (culled to 5/position after)

## Gameplay
- [x] League leaders — split Defense into sub-sections (Tackles / Sacks / Interceptions) instead of single tackles-sorted list
- [ ] Trade — player-for-player and n-for-n trades
- [ ] --POST LAUNCH-- CPU proactive roster upgrades — today CPUs only fill *open* slots (injury/hole), never upgrade a full roster, so good players pile up unclaimed in FA (this feeds the human's "gems" edge). Plan: let CPUs occasionally release a clearly-weak starter to sign a clearly-better FA. Timing is already handled — `run_cpu_roster_moves` runs at the *start* of each week (`league_service.py:634`) so human coaches get first crack at FAs after the previous week's injuries. Open tuning: how aggressive, and a gap threshold so CPUs don't churn. NOTE: CPU moves now write to the transactions feed, so proactive upgrades will show up there automatically once added.
- [ ] --POST LAUNCH-- Trade — "Offer for Trade" from own roster (button commented out on RosterScreen)
- [ ] --POST LAUNCH-- Trade — trade for draft pick
- [x] Team history view — season-by-season W/L record tied to team_id, survives name changes
- [x] Team names unique per league (validation on rename + league creation)
- [x] Scoring play log — requires sim changes to record plays in sequence + new DB table; natural companion to game detail screen

## Social
- [x] League message board — built 2026-07-27: **flat** feed, **all-time** league-wide archive, post-as-team (team + coach name snapshot), author soft-delete (`deleted_at`). Keyset cursor pagination + infinite scroll (reuses the transactions pattern). Model `LeagueMessage` + migration `b8d3f1a6c9e2`; endpoints `GET/POST /{league}/messages` + `DELETE /{league}/messages/{id}`; `message_board_screen.dart` + nav button. Resolved the open design Qs: flat over threaded, all-time over per-season, author-delete (no commissioner/report yet). PENDING: new-post push notification (the "then push" tie-in).

## Engagement
- [x] Game plan — weekly OFF/DEF setting (Balanced / Run Focus / Pass Focus; Balanced / Run Stop / Pass Rush); resets to Balanced each week advance so user must actively choose; set on the matchup screen pre-game; sim reads it and applies play-call probability + stat modifiers; CPU teams get a plan too (random or composite-based)
- [x] Team news feed — single current-week headline computed on the fly from live data (no DB table); sources: last result, W/L streak, playoff position, injuries, star player performance; shown on team home screen above or within the alerts card
- [x] Team news — playoff spectator mode: once a team is eliminated, news slot shows league-wide playoff coverage (conference championship matchup previews → league championship preview → champion announcement); both conferences shown regardless of which conference your team is in
- [x] Push notification on game simmed — fires from cron immediately after the human coach's game resolves; message: "Your [team] just [won/lost/tied] [score] against [opponent]. Open the app to see the box score."

## Verify / Bugs (season 3)
- [x] Push notifications — not confirmed working end of season 2; verify a game notification fires this season
- [x] Playoff team news — spectator mode headlines may not have been showing correctly for eliminated teams
- [x] Transactions list — fixed: _current_season_id was filtering out complete seasons, writing NULL season_id during preseason; verify transactions appear this season

## Polish
- [ ] Visual identity — team `color1` / `color2` fields for UI theming; player `jersey_number` field; requires DB migration
- [ ] Push notifications — IR returns, season phase changes (expand scope once game-simmed notification is built)

## Monetization
- [ ] Monetization — free first league, paid additional leagues; payment flow TBD

## --POST LAUNCH-- Stats & History
- [ ] --POST LAUNCH-- All-time league statistical leaders — season records for passing yards, rush yards, receiving yards, TDs, sacks, interceptions, etc.; powered by existing career_stats + retired player records

## --POST LAUNCH-- Draft & League
- [ ] --POST LAUNCH-- Live draft — real-time snake draft session for private leagues; per-pick countdown timer; auto-pilot fallback from preference queue when timer expires; CPU teams auto-pick instantly; live and auto-pilot coaches coexist

## --POST LAUNCH-- Game Modes
- [ ] Fantasy contest mode — fully CPU-simmed league; each user picks 2 QB / 2 RB / 2 WR / 2 TE / 2 D (individual player, any position) per week from any team; multiple users can share the same players; fantasy points from game stats accumulate across the season; most points wins.
  - D slot: individual player (any defensive position) or team defense unit? Individual fits existing stat model better.
  - Scoring weights: define points table (e.g. pass yds, pass TD, rush yds, rush TD, receptions, tackles, sacks, INTs, etc.)
  - Pick lock: when do picks lock — before each week advances, or a fixed real-time deadline?
  - League source: dedicated CPU-only league per contest, or fantasy overlay on top of an existing regular league?

## --POST LAUNCH-- League Variants & Inclusivity
- [ ] --POST LAUNCH-- Women's leagues — option for all-female-player leagues, inspired by real women's tackle football (WNFC); adds representation for an underrepresented group and a fresh flavor without new mechanics.
  - Scope: same sim engine and attributes — purely representational (female name pool, and player art/jersey later if visual identity ships). No engine difference; avoids implying different capability.
  - Opt-in model: league-type choice at creation (e.g. a "Women's league" option) rather than a global or forced setting — additive content that costs nothing to players uninterested in it.
  - Positioning/copy: present as a celebratory, optional league flavor, not a political statement; let players self-select. Anticipate mixed community reception ("that's cool" vs. "should be men only") — the opt-in framing is the mitigation: it's one more league to choose, not a change to anyone's existing experience.
  - Naming: draw inspiration from WNFC but keep original league/team theming (same reason we avoid NFL marks).
  - Open questions: mixed-league support at all, or strictly separate? surface as a filter on the join/available-leagues screen? any distinct league/conference name theme pool?

## Long-term / v3
- [x] Randomized league/conference/division names — pool of curated theme families (Storm, Celestial, Geological, Ocean, Fire, etc.), each with 6 names; at league creation pick one theme at random, assign 1 name to league, 2 to conferences, 4 to divisions (no repeats); conference and division names are thematic peers, not a strict hierarchy; pool is easy to extend; requires storing generated names on League/Team models
- [x] Aging, decline, and retirement — age curves, fitness-weighted stat decay, retirement threshold (floor ~45 composite)
- [x] Annual draft class — smaller than season 1 pool (~60–70% size) to avoid FA pool inflation
- [x] FA pool management — roster-less decline: players in FA at end of season take an extra decline tick on top of normal age decay; players below composite floor retire out of the pool entirely; active signings by CPU + human drain mid-tier naturally
- [ ] --POST LAUNCH-- Cross-League Championship — Champions League style; season winners enter a playoff pool every 2–3 months, set starters, sim only
