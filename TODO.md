# Gridiron Empire — To-Do

## Up Next
- [x] Team rename — PATCH endpoint + UI on team home screen
- [ ] Season 2+ (no draft) — offseason → new season flow; clear old games, generate new schedule, reset week; players keep current rosters
- [ ] Draft system — annual draft class; no roster limit immediately post-draft, but rosters must be trimmed to active limit before season start

## Gameplay
- [ ] League leaders — split Defense into sub-sections (Tackles / Sacks / Interceptions) instead of single tackles-sorted list
- [ ] Trade — "Offer for Trade" from own roster (stub exists in player detail sheet on RosterScreen)
- [ ] Trade — n-for-n trades (post-v1)
- [ ] Team history view — season-by-season W/L record tied to team_id, survives name changes
- [x] Team names unique per league (validation on rename + league creation)
- [ ] Scoring play log — requires sim changes to record plays in sequence + new DB table; natural companion to game detail screen

## Polish
- [ ] Visual identity — team `color1` / `color2` fields for UI theming; player `jersey_number` field; requires DB migration
- [ ] Push notifications — alternative/supplement to the alerts board for IR returns, season phase changes

## Long-term / v3
- [ ] Aging, decline, and retirement — age curves, fitness-weighted stat decay, retirement threshold
- [ ] Annual draft class — generated rookie pool each offseason
- [ ] Cross-League Championship — Champions League style; season winners enter a playoff pool every 2–3 months, set starters, sim only
