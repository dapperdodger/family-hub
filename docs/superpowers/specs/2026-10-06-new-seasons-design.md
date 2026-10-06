# New seasons: program design

Follow-up to seasonal Lite (hub PR #18). Adds Winter, Spring, Summer and most major US holidays to the
seasonal looks, in three pull requests. Read `docs/seasonal-looks.md` first: every look is held to that
standard (real licence-clean photos, no generated art, no clip-art props, no emoji decoration, the
owner picks from real screenshots, and Lite must cover every moving part).

## Intent

A wall that follows the whole year, not just September to November. Each season is a real photograph
behind the usual glass cards, with a matching accent, a small season mark by the wordmark and, where
it suits, one gentle kind of motion. Everything stays Pi-3-safe: new motion lives in the layers Lite hides.

## Decisions (operator, 2026-10-06)

- **Three PRs, in this order:** (1) groundwork, (2) the broad seasons (Winter, Spring, Summer),
  (3) the holidays. Thanksgiving (Nov 16) and Christmas (Dec 1) are in PR 3, so this year they may miss
  their dates (Winter covers December meanwhile); they then show from next year. Operator chose this
  with the dates in view.
- **Holidays in scope:** Thanksgiving, Christmas, New Year's, Martin Luther King Jr. Day, Valentine's
  Day, St Patrick's Day, Easter, Mother's Day, Father's Day, Fourth of July. (Halloween and
  Fall already exist.) **Not now:** Memorial Day, Labor Day, Veterans Day, Presidents' Day: they can be
  added later by the same recipe.
- **Looks per season, by window length:** the long ones (Winter, Spring, Summer, Christmas, Thanksgiving,
  Fourth of July) get 3 looks; the short ones (New Year's, Valentine's, St Patrick's, Easter, Mother's Day,
  Father's Day, MLK Day) get 1 or 2. About 30 photos in all.
- **Motion:** one gentle kind per season, photo only for the solemn ones.

| Season | Window (first match wins; holidays are listed before the broad season they sit in) | Motion |
|---|---|---|
| New Year's | Dec 27 to Jan 2 (wraps the year) | slow golden sparkle |
| Christmas | Dec 1 to Dec 26 | soft snow |
| MLK Day | the Friday to the Monday of the third Monday in January (moving) | photo only |
| Valentine's Day | Feb 1 to Feb 14 | drifting petals |
| Winter | Dec 1 to Feb 29 (the rest of it) | soft snow |
| St Patrick's Day | Mar 1 to Mar 17 | drifting clover-leaf silhouettes |
| Easter | the 14 days before Easter Sunday, through Easter Monday (moving) | drifting petals |
| Mother's Day | the Monday to the Sunday of the second Sunday in May (moving) | drifting petals |
| Spring | Mar 1 to May 31 (the rest of it) | drifting petals |
| Father's Day | the Thursday to the Sunday of the third Sunday in June (moving) | photo only |
| Fourth of July | Jun 25 to Jul 4 | slow sparkle |
| Summer | Jun 1 to Aug 31 (the rest of it) | fireflies at dusk |
| Halloween | Oct 1 to Oct 31 (existing) | existing |
| Thanksgiving | the Monday 10 days before to the Sunday after the fourth Thursday in November (moving) | the fall leaves |
| Fall | Sep 1 to Nov 30 (existing) | existing |

Order in the registry matters (first window that matches today wins): New Year's, Christmas, MLK Day,
Valentine's, Winter; St Patrick's, Easter, Mother's Day, Spring; Father's Day, Fourth of July,
Summer; Halloween, Thanksgiving, Fall. Christmas is listed before Thanksgiving so a late Thanksgiving
week that touches Dec 1 yields to Christmas. Today's two overlaps are intentional and tested.

**Rulings after the PR 1 review (2026-10-06).** Juneteenth is dropped (the operator could not think of good
photos for it, and its window swallowed Father's Day in most years). **Season ids are bare lowercase words**
(`newyears`, `mlkday`, `stpatricks`, `mothersday`, `fathersday`, `julyfourth`), because the static guards treat
every hyphenated id as a look; a look's id is `<seasonid>-<name>`. The picker's third group is "More seasons"
(it holds what is not in season and not coming up soon, so "All seasons" would misdescribe it).

## PR 1: groundwork

1. **Moving windows.** A season may carry `window(year) -> {from: [m, d], to: [m, d]}` instead of fixed
   `from`/`to` (Easter uses the standard Gregorian computus; the "nth weekday" holidays a small helper).
   `inWindow` evaluates it for the year of the date being asked about, wrapping across New Year as it
   already does. A season also carries `when` text for Settings ("Around Easter", "The week of Mother's
   Day") since a fixed "Oct 1 to Oct 31" does not exist for it. `nextSeason()` ("Fall starts Sep 1") works
   with moving windows. Tests pin the dates for several years, including the earliest and latest Easter.
2. **A real "which look paints" test across the whole calendar.** A table-driven test asserts the season
   for representative dates through the year (every window's first and last day, the overlaps, the leap
   day, Dec 31 and Jan 1), so a future window edit cannot silently drop a day or two seasons overlap by
   accident.
3. **The Settings picker scales.** With about 15 seasons the list is long. Group it: **In season now**
   (open), **Coming up** (the next few, collapsed), **All seasons** (collapsed). Tiles keep their
   live-preview look. Every season stays reachable; picking a look in any group works as today.
4. **Drift layers for the new motion.** A generic drifting-particle layer (the same machinery as the
   leaves: one outer span falls or floats at constant speed, an inner one sways) driven by CSS tokens for
   its shape, size, speed and colour: snow (soft round flakes), petals, clover-leaf silhouettes, fireflies
   (slow pulsing dots that wander), sparkle (small fading points). Shapes are masks cut from public-domain
   or self-made abstract SVG (flakes and petals are shapes, not props); nothing is drawn as a scene. They
   live in the layers Lite already hides (a new far layer inside `.season`, a new near layer inside
   `.season-fx`), are compositor-only (`transform`/`opacity`), stop for reduced motion and at night, and
   are sized through `--sn-k`.
5. **Season marks.** The mark by the wordmark is a one-colour mask. Each new season gets its own
   (snowflake, petal, sun, clover leaf, star, heart, ...) as an SVG in `static/seasons/`, credited or
   self-made.
6. **Guards extended.** `LITE_COVERS` gains the new motion classes; the tests that every look sets its
   photo, accent and mark, and never a theme-owned token, run over the new seasons as they are added; a
   test that every season has a `when` text or fixed window.

PR 1 ships no new photos, so nothing changes on a wall until PR 2. The picker grouping and the window
tests are exercised with the existing two seasons plus test-only fixtures.

## PRs 2 and 3: each season

Per season: 1. **Source** a contact sheet of licence-clean candidates (NPS, Wikimedia Commons, Unsplash
and similar, per section 5 of the standard), shown as real screenshots on the wall. 2. **You pick**
(never guessed on your behalf). 3. **Build** the looks: photo (`prep-season-photo.py`, 2560px, never
softened), `CREDITS.md` row, registry entry, CSS token block (photo, focal point, accent), mark, motion
set. 4. **Check by eye** at full size: every look x all five themes, seasons off, night, reduced motion,
Lite on, the phone, the gear popover, the Settings tiles, and seasons-off pixel-for-pixel against main.
5. Gauntlet: tests, changelog bullet, README, `docs/seasons.jpg` refreshed, reviews. Each of PR 2 and PR 3
gets its own plan (and the contact sheets) when we reach it.

## Out of scope

Memorial Day, Labor Day, Veterans Day, Presidents' Day; per-region or non-US holidays; user-uploaded
photos; automatic photo rotation within a season; any new motion that is not a small shape drifting in
the existing layers.

## Budget and risks

- **Art size:** the 8 existing looks are about 6 MB; about 30 more at 0.7 to 2 MB is roughly 25 to 50 MB
  added to the repo and the image. Acceptable for the home network; noted so it is a choice, not a surprise.
- **Contact sheets are the long pole:** about 14 seasons of sourcing and picking. PR 2 is 3 seasons; PR 3
  is 11 and may itself be split by the operator into two review sittings.
- **Moving windows are the correctness risk:** they get table-driven tests across many years.
- **Pi 3:** every new motion lives in layers Lite hides, and the Lite look of each new season is checked
  by eye like every other combination.

## Testing

Pure date maths (Easter, nth weekday, wrapping windows) unit-tested for several years including edge
years; the whole-calendar season table; picker grouping DOM tests; the existing static guards extended;
browser checks per the standard.
