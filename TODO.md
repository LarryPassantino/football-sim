# Gridiron Empire — To-Do

## Up Next
- [x] Reduce OFFSEASON_DAYS from 4 to 3 (backend/app/services/league_service.py)
- [x] Team rename — PATCH endpoint + UI on team home screen
- [x] Season 2+ (no draft) — offseason → new season flow; clear old games, generate new schedule, reset week; players keep current rosters
- [x] Draft system — annual draft class; 5 rounds, worst→best linear order; CPU auto-picks; human picks via Draft Room; undrafted go to FA pool (culled to 5/position after)

## Gameplay
- [x] League leaders — split Defense into sub-sections (Tackles / Sacks / Interceptions) instead of single tackles-sorted list
- [ ] Trade — player-for-player and n-for-n trades
- [ ] --POST LAUNCH-- CPU roster moves — currently only fills open slots (injury-triggered); revisit proactive upgrades (release weak player, sign better FA) if CPU-heavy leagues need it
- [ ] --POST LAUNCH-- Trade — "Offer for Trade" from own roster (button commented out on RosterScreen)
- [ ] --POST LAUNCH-- Trade — trade for draft pick
- [x] Team history view — season-by-season W/L record tied to team_id, survives name changes
- [x] Team names unique per league (validation on rename + league creation)
- [x] Scoring play log — requires sim changes to record plays in sequence + new DB table; natural companion to game detail screen

## Social
- [ ] League message board — coaches can post text messages visible to all coaches in the league; persistent across the season; natural home for trade talk, trash talk, and draft reactions; open design questions: threaded vs. flat, moderation, per-season vs. all-time archive

## Engagement
- [x] Game plan — weekly OFF/DEF setting (Balanced / Run Focus / Pass Focus; Balanced / Run Stop / Pass Rush); resets to Balanced each week advance so user must actively choose; set on the matchup screen pre-game; sim reads it and applies play-call probability + stat modifiers; CPU teams get a plan too (random or composite-based)
- [x] Team news feed — single current-week headline computed on the fly from live data (no DB table); sources: last result, W/L streak, playoff position, injuries, star player performance; shown on team home screen above or within the alerts card
- [x] Team news — playoff spectator mode: once a team is eliminated, news slot shows league-wide playoff coverage (conference championship matchup previews → league championship preview → champion announcement); both conferences shown regardless of which conference your team is in
- [x] Push notification on game simmed — fires from cron immediately after the human coach's game resolves; message: "Your [team] just [won/lost/tied] [score] against [opponent]. Open the app to see the box score."

## Verify / Bugs (season 3)
- [x] Push notifications — not confirmed working end of season 2; verify a game notification fires this season
- [ ] Playoff team news — spectator mode headlines may not have been showing correctly for eliminated teams
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

## Long-term / v3
- [x] Randomized league/conference/division names — pool of curated theme families (Storm, Celestial, Geological, Ocean, Fire, etc.), each with 6 names; at league creation pick one theme at random, assign 1 name to league, 2 to conferences, 4 to divisions (no repeats); conference and division names are thematic peers, not a strict hierarchy; pool is easy to extend; requires storing generated names on League/Team models
- [x] Aging, decline, and retirement — age curves, fitness-weighted stat decay, retirement threshold (floor ~45 composite)
- [x] Annual draft class — smaller than season 1 pool (~60–70% size) to avoid FA pool inflation
- [x] FA pool management — roster-less decline: players in FA at end of season take an extra decline tick on top of normal age decay; players below composite floor retire out of the pool entirely; active signings by CPU + human drain mid-tier naturally
- [ ] --POST LAUNCH-- Cross-League Championship — Champions League style; season winners enter a playoff pool every 2–3 months, set starters, sim only
