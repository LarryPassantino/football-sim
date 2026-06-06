# Gridiron Empire — UI Design Context
*Bring this into Claude Code to continue UI work with full context.*

---

## The Game

**Gridiron Empire** is an American football management sim for iOS and Android (phone + tablet), built in Flutter/Dart. It is intentionally lighter on complex management mechanics than competitors — the core loop is **roster management and simulation only**. No match view, no tactical pitch, no play-calling. Think persistent league, draft, and sim.

It is one of several projects under the **Empty Crowds Collective** brand (`emptycrowds.app`), a solo indie dev operation. Prior apps have had a flat, tool-like aesthetic. This project is the first that needs to feel like a *game*.

---

## Visual Direction

### The Core Challenge
The app is data-rich (53-player rosters, depth charts, stats) but needs to feel like a game rather than a SaaS dashboard. The upgrade is not adding complexity — it's adding *personality and atmosphere* to the shell around clean data.

### Three Concepts Were Explored

**A — Broadcast Dark**
Deep navy (`#0a0e1a`) with amber accents (`#f59e0b`), condensed type (Bebas Neue / Barlow Condensed), faint grid overlay. Feels like a Sky Sports or ESPN broadcast overlay. Color-coded OVR ratings, morale bars, status badges. Clean and premium.

**B — Matchday Programme**
Off-white (`#f5f0e8`) with ink-heavy print aesthetic, Playfair Display + Instrument Serif. Like a 1970s football programme. Two-column layout with sidebar. Very distinctive — but the editorial layout depends on wider viewports and may be harder to adapt to phone portrait. Lowest priority for mobile.

**C — Chalkboard**
Dark slate (`#1c2028`) with chalk-style rendering, Oswald typeface, faint noise texture, green pitch undertones, amber/gold accents. Mini attribute bars per player row. Feels like a coach's analysis board. Geometric and structured — translates most naturally to Flutter.

**Concepts A and C are the strongest candidates** for phone + tablet. B is a stretch on narrow viewports.

### Shared Visual Language (across all concepts)
- Position group headers as section dividers (Offense / Defense / Special Teams)
- SVG jersey component with dynamic team colors and number — the primary player avatar
- Status badges (Fit / Injured / Day-to-day / Suspended) with color coding
- OVR rating as the dominant numeric element per player
- Staggered row entrance animations on load

---

## Flutter Implementation Notes

### Layout Strategy: Two Distinct Layouts
Do **not** try to scale one layout from phone to tablet. Use `LayoutBuilder` to serve different widget trees:

- **Tablet**: Full table layout — jersey, name, position, age, key attributes, OVR, status in a row. Concepts A and C shine here.
- **Phone (portrait)**: Card-per-player layout. Jersey + number left, name/position/key stats center, OVR prominent right. Tap to open detail view.

### Position Group Headers
With 53 players, section headers (Offense / Defense / Special Teams, or by position unit: QB, RB, WR/TE, OL, DL, LB, DB, ST) are essential for navigation — especially on phone where it's a lot of scroll. These should be visually chunky and distinct from player rows.

### Depth Chart View
Consider making the **depth chart** the primary view rather than a flat roster list — QB1 / QB2 / QB3 stacked per position slot is how coaches and fans actually think. This is a more natural frame for American football than soccer.

### Jersey Component
- Render via SVG (`flutter_svg` package) — keep as SVG assets, color-swap team colors dynamically by replacing fill values
- Shape: simple jersey silhouette with collar, sleeves, number on chest
- Accent stripe (yoke/shoulder) changes with team secondary color
- Number rendered in team font style

### Key Flutter Approaches
- `CustomPainter` for attribute bars, any custom drawing
- `AnimationController` + staggered `AnimationDelay` for row entrance animations
- `ThemeData` / CSS-variable-equivalent for team color system
- `flutter_svg` for jersey assets
- No horizontal scroll on phone — if a column doesn't fit, it gets dropped or moved to detail view

---

## Data Model (Roster)

Each player has at minimum:
- Jersey number
- Name
- Position (abbreviated: QB, RB, WR, TE, OL, DL, LB, CB, S, K, P)
- Age
- Overall rating (OVR, 0–99)
- Status: Active / Injured / Day-to-day / Suspended
- Contract info (year, salary — for roster management decisions)
- Key attributes (vary by position — speed/physical/technique or equivalent)
- Morale (0.0–1.0)
- Appearances / stats for current season

Position groupings for section headers:
- **Offense**: QB, RB, WR, TE, OL
- **Defense**: DL, LB, CB, S
- **Special Teams**: K, P, LS

---

## Reference HTML Prototype

A working HTML/JS prototype of all three roster concepts was built, including:
- Animated row entrance (staggered)
- SVG jersey component with number
- OVR color coding (green ≥80, amber 74–79, red <74)
- Status badge system
- Morale bar (Concept A)
- Attribute bars with per-attribute color coding (Concept C)
- Position + name display

The prototype uses these fonts (available on Google Fonts):
- `Bebas Neue` — display numbers, team name (Concept A)
- `Barlow Condensed` — player names, labels (Concept A)
- `IBM Plex Mono` — column headers, tags, metadata (all concepts)
- `Playfair Display` — editorial headings (Concept B)
- `Instrument Serif` — italic body (Concept B)
- `Oswald` — team name, player names (Concept C)

Flutter font equivalents to source or approximate:
- Bebas Neue: available on Google Fonts, works in Flutter
- Barlow Condensed: available on Google Fonts
- IBM Plex Mono: available on Google Fonts
- Oswald: available on Google Fonts

---

## Immediate Next Steps (suggested)

1. Decide on Concept A vs C as the primary direction (or a hybrid)
2. Build the Flutter `PlayerRowCard` widget (phone layout) and `PlayerTableRow` widget (tablet layout)
3. Build the `JerseyWidget` SVG component with dynamic color props
4. Build the position group section header widget
5. Wire up a `LayoutBuilder` roster screen that switches between card and table layouts
6. Define `ThemeData` with team color slots (primary, secondary, text)

---

## Brand Context

- Developer: Empty Crowds Collective / `emptycrowds.app`
- Other active projects: Pulse (energy journal), Conspire (convention social tool)
- Design sensibility: dry wit, "less is more," intentional — avoid bloat
- No AI-generated art; logos and marks are hand-crafted (Inkscape)
- SVG rendering in code is fine and preferred over raster assets where possible
