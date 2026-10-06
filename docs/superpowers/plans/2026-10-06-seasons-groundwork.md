# New Seasons, PR 1: Groundwork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything the new seasons need that is not a photo: moving-date holiday windows, a registry that can carry them, a Settings picker that stays usable with ~15 seasons, one generic gentle-motion layer (snow, petals, clover leaves, fireflies, sparkle), and a free-photo search helper for the later PRs.

**Architecture:** `theme.js` gains pure date helpers and named window recipes (Easter, Mother's/Father's Day, MLK Day, Thanksgiving), a registry that accepts `window(year)`, `when` and `drift` per season, a `seasonOutlook()` for the picker, and stamps `data-drift` next to `data-look`. `hub.js` groups the Settings tiles and mounts one generic drift layer; `styles.css` styles the five kinds under the existing Lite-hidden layers. A dev-only script searches open sources for photo candidates and writes a contact sheet.

**Tech Stack:** vanilla JS (`theme.js`, `hub.js`), CSS, node:test, pytest, Python stdlib for the search helper.

**Spec:** `docs/superpowers/specs/2026-10-06-new-seasons-design.md`

## Global Constraints

- PR 1 ships NO new seasons, looks or photos: with the existing Fall and Halloween nothing changes on a wall except the Settings picker's grouping.
- A holiday is listed before the broad season it sits in; the first window that matches today wins. Registry order is: New Year's, Christmas, MLK Day, Valentine's, Winter; St Patrick's, Easter, Mother's Day, Spring; Juneteenth, Father's Day, Fourth of July, Summer; Halloween, Thanksgiving, Fall.
- Window recipes (exact): Easter = the 14 days before Easter Sunday through Easter Monday; Mother's Day = Monday through the 2nd Sunday of May; Father's Day = Thursday through the 3rd Sunday of June; MLK Day = Friday through the 3rd Monday of January; Thanksgiving = the Monday 10 days before through the Sunday after the 4th Thursday of November. Fixed ones: New Year's Dec 27 to Jan 2, Christmas Dec 1 to Dec 26, Valentine's Feb 1 to 14, Winter Dec 1 to Feb 29, St Patrick's Mar 1 to 17, Spring Mar 1 to May 31, Juneteenth Jun 12 to 19, Fourth of July Jun 25 to Jul 4, Summer Jun 1 to Aug 31.
- Drift kinds are exactly `snow`, `petal`, `clover`, `firefly`, `sparkle`. Shapes are abstract masks or gradients, never scenes, clip-art props or emoji. Motion is `transform`/`opacity` only, hidden by Lite, stopped for reduced motion, paused at night, sized through `--sn-k`.
- Photo sources follow `docs/seasonal-looks.md` section 5 (operator decision 2026-10-06: **keep the rule**: no current Unsplash, Pexels or Pixabay). The search helper only searches sources that satisfy it and only keeps public-domain/CC0 results.
- Every new file in `static/seasons/` gets a `CREDITS.md` row (a test enforces it); self-made shapes are credited as "self-made, CC0".
- Custom CSS classes must be styled (`test_every_referenced_class_is_styled`). Each src commit adds its own NEW "- " bullet under CHANGELOG `## [Unreleased]` (hook). Public repo: no real IPs or tokens.
- Run Python with the scratchpad venv, `TZ=UTC`, `PYTHONUTF8=1`; 49 Python tests fail identically on clean main on Windows (backup 30, install_hooks 13, caldav 2, google_client 2, check_changelog 1, api health 1). Write multi-line edit scripts to a file with the Write tool (the shell halves backslashes).

## Review Focus

- Moving windows across years: Easter at its earliest/latest, a Thanksgiving window that touches Dec 1 (Christmas must win), Easter overlapping St Patrick's (St Patrick's wins Mar 1 to 17), Father's Day overlapping Juneteenth (Juneteenth wins), the leap day, Dec 31 / Jan 1.
- A new `drift` value, a typo'd one, or a season without one: `data-drift` is always `none` or a known kind, and always matches the painted look (never stale after the look changes or season goes off).
- The picker: every season appears exactly once; the in-season season is open and marked; a collapsed group's tiles still work; the existing two seasons behave as before (pick, aria-pressed, preview).
- Drift under Lite, reduced motion, night, the phone, and in Settings tiles (resting, not animating): nothing keeps animating when it should not.
- The search helper never keeps a result whose licence is not public domain / CC0, never downloads without being asked, and the contact sheet escapes everything it prints.

---

### Task 1: Date helpers, window recipes and the moving-window registry

**Files:**
- Modify: `src/family_hub/web/static/theme.js`
- Create: `tests/js/seasons.test.mjs`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces (all on `window.FH_SEASON_TOOLS`): `nthWeekday(year, month, weekday, n) -> dayOfMonth`, `easterSunday(year) -> [m, d]`, `windows` = `{easter, mothersDay, fathersDay, mlkDay, thanksgiving}` each `(year) -> {from: [m, d], to: [m, d]}`, `windowOf(season, year) -> {from, to}`, `inWindow(season, date) -> bool`, `seasonFor(date, list = SEASONS) -> season | null`, `seasonOutlook(date, list = SEASONS) -> {active: [season], upcoming: [season], rest: [season]}`. A season may carry `window: fn(year)` instead of `from`/`to`, plus `when: "text"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/seasons.test.mjs`:

```javascript
// Executable tests for the season date machinery in theme.js (moving holiday windows, the
// whole-calendar season table, the picker's outlook). theme.js is loaded into a vm sandbox like
// theme.test.mjs does; no network, no storage needed beyond a stub.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const staticDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'src', 'family_hub', 'web', 'static');
const themeSrc = readFileSync(join(staticDir, 'theme.js'), 'utf8');

function loadTools() {
  const attrs = {};
  const root = { setAttribute(k, v) { attrs[k] = String(v); }, getAttribute(k) { return k in attrs ? attrs[k] : null; } };
  const store = new Map();
  const win = { localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) } };
  const sandbox = { window: win, document: { documentElement: root } };
  vm.createContext(sandbox);
  vm.runInContext(themeSrc, sandbox);
  return win.FH_SEASON_TOOLS;
}
const T = loadTools();
const md = (v) => Array.from(v);
const d = (s) => { const [y, m, day] = s.split('-').map(Number); return new Date(y, m - 1, day); };

test('nthWeekday: Mother\'s Day, Father\'s Day, MLK Day and Thanksgiving fall where the calendar says', () => {
  assert.equal(T.nthWeekday(2026, 5, 0, 2), 10, '2nd Sunday of May 2026');
  assert.equal(T.nthWeekday(2026, 6, 0, 3), 21, '3rd Sunday of June 2026');
  assert.equal(T.nthWeekday(2027, 1, 1, 3), 18, '3rd Monday of January 2027');
  assert.equal(T.nthWeekday(2026, 11, 4, 4), 26, '4th Thursday of November 2026');
  assert.equal(T.nthWeekday(2027, 11, 4, 4), 25, '4th Thursday of November 2027');
  assert.equal(T.nthWeekday(2030, 11, 4, 4), 28, 'the latest Thanksgiving there can be');
});

test('easterSunday matches the published dates, earliest and latest included', () => {
  const published = { 2008: [3, 23], 2013: [3, 31], 2024: [3, 31], 2025: [4, 20], 2026: [4, 5], 2027: [3, 28], 2038: [4, 25] };
  for (const [y, want] of Object.entries(published)) assert.deepEqual(md(T.easterSunday(Number(y))), want, y);
});

test('the named window recipes', () => {
  const w = (f, y) => { const r = f(y); return [md(r.from), md(r.to)]; };
  assert.deepEqual(w(T.windows.easter, 2026), [[3, 22], [4, 6]], '14 days before Apr 5 through Easter Monday');
  assert.deepEqual(w(T.windows.easter, 2024), [[3, 17], [4, 1]]);
  assert.deepEqual(w(T.windows.mothersDay, 2026), [[5, 4], [5, 10]], 'Monday to the 2nd Sunday of May');
  assert.deepEqual(w(T.windows.fathersDay, 2026), [[6, 18], [6, 21]], 'Thursday to the 3rd Sunday of June');
  assert.deepEqual(w(T.windows.mlkDay, 2027), [[1, 15], [1, 18]], 'Friday to the 3rd Monday of January');
  assert.deepEqual(w(T.windows.thanksgiving, 2026), [[11, 16], [11, 29]], 'Monday 10 days before to the Sunday after');
  assert.deepEqual(w(T.windows.thanksgiving, 2030), [[11, 18], [12, 1]], 'a window may run into December');
});

// The year-round layout the new seasons will fill (spec: docs/superpowers/specs/2026-10-06-new-seasons-design.md).
// Order matters: the first window that matches wins.
const PLAN = [
  { id: 'new-years', from: [12, 27], to: [1, 2] },
  { id: 'christmas', from: [12, 1], to: [12, 26] },
  { id: 'mlk', window: (y) => T.windows.mlkDay(y) },
  { id: 'valentines', from: [2, 1], to: [2, 14] },
  { id: 'winter', from: [12, 1], to: [2, 29] },
  { id: 'st-patricks', from: [3, 1], to: [3, 17] },
  { id: 'easter', window: (y) => T.windows.easter(y) },
  { id: 'mothers-day', window: (y) => T.windows.mothersDay(y) },
  { id: 'spring', from: [3, 1], to: [5, 31] },
  { id: 'juneteenth', from: [6, 12], to: [6, 19] },
  { id: 'fathers-day', window: (y) => T.windows.fathersDay(y) },
  { id: 'july4', from: [6, 25], to: [7, 4] },
  { id: 'summer', from: [6, 1], to: [8, 31] },
  { id: 'halloween', from: [10, 1], to: [10, 31] },
  { id: 'thanksgiving', window: (y) => T.windows.thanksgiving(y) },
  { id: 'fall', from: [9, 1], to: [11, 30] },
];
const on = (s) => { const r = T.seasonFor(d(s), PLAN); return r ? r.id : null; };

test('the whole-calendar table: every window edge, every overlap, the leap day, New Year', () => {
  const table = {
    '2026-12-27': 'new-years', '2027-01-01': 'new-years', '2027-01-02': 'new-years', '2027-01-03': 'winter',
    '2027-01-14': 'winter', '2027-01-15': 'mlk', '2027-01-18': 'mlk', '2027-01-19': 'winter',
    '2026-12-01': 'christmas', '2026-12-26': 'christmas', '2026-12-31': 'new-years',
    '2027-02-01': 'valentines', '2027-02-14': 'valentines', '2027-02-15': 'winter', '2028-02-29': 'winter',
    '2026-03-01': 'st-patricks', '2026-03-17': 'st-patricks', '2026-03-21': 'spring',
    '2026-03-22': 'easter', '2026-04-06': 'easter', '2026-04-07': 'spring',
    '2024-03-17': 'st-patricks', '2024-03-18': 'easter', '2024-04-01': 'easter',
    '2026-05-03': 'spring', '2026-05-04': 'mothers-day', '2026-05-10': 'mothers-day', '2026-05-11': 'spring',
    '2026-05-31': 'spring', '2026-06-01': 'summer', '2026-06-11': 'summer',
    '2026-06-12': 'juneteenth', '2026-06-19': 'juneteenth', '2026-06-20': 'fathers-day', '2026-06-21': 'fathers-day',
    '2026-06-22': 'summer', '2026-06-25': 'july4', '2026-07-04': 'july4', '2026-07-05': 'summer', '2026-08-31': 'summer',
    '2026-09-01': 'fall', '2026-10-01': 'halloween', '2026-10-31': 'halloween', '2026-11-01': 'fall',
    '2026-11-15': 'fall', '2026-11-16': 'thanksgiving', '2026-11-29': 'thanksgiving', '2026-11-30': 'fall',
    '2030-12-01': 'christmas',
  };
  for (const [day, want] of Object.entries(table)) assert.equal(on(day), want, day);
});

test('every day of several years belongs to some season (no gaps), including leap years', () => {
  for (const year of [2026, 2027, 2028, 2031]) {
    for (let t = new Date(year, 0, 1); t.getFullYear() === year; t = new Date(year, t.getMonth(), t.getDate() + 1)) {
      assert.ok(T.seasonFor(t, PLAN), `${t.toDateString()} has a season`);
    }
  }
});

test('seasonFor on the real registry still answers Halloween then Fall as before', () => {
  assert.equal(T.seasonFor(d('2026-10-06')).id, 'halloween');
  assert.equal(T.seasonFor(d('2026-11-05')).id, 'fall');
  assert.equal(T.seasonFor(d('2026-07-15')), null, 'nothing is in season in July yet');
});

test('seasonOutlook groups the picker: what is in season, what comes next by date, the rest', () => {
  const fixture = [
    { id: 'a', from: [10, 1], to: [10, 31] }, { id: 'b', from: [9, 1], to: [11, 30] },
    { id: 'easter', window: (y) => T.windows.easter(y) }, { id: 'c', from: [12, 1], to: [12, 26] },
    { id: 'e', from: [2, 1], to: [2, 14] }, { id: 'f', from: [6, 12], to: [6, 19] },
  ];
  const o = T.seasonOutlook(d('2026-10-06'), fixture);
  assert.deepEqual(o.active.map((s) => s.id), ['a', 'b'], 'both windows hold today, registry order');
  assert.deepEqual(o.upcoming.map((s) => s.id), ['c', 'e', 'easter'], 'the next three to start, soonest first');
  assert.deepEqual(o.rest.map((s) => s.id), ['f'], 'everything else, registry order');
});

test('seasonOutlook with nothing in season lists the next ones; a moving window is found next year', () => {
  const fixture = [{ id: 'easter', window: (y) => T.windows.easter(y) }, { id: 'c', from: [12, 1], to: [12, 26] }];
  const o = T.seasonOutlook(d('2026-04-20'), fixture);   // Easter 2026 has passed: next is Dec 1, then Easter 2027
  assert.deepEqual(o.active, []);
  assert.deepEqual(o.upcoming.map((s) => s.id), ['c', 'easter']);
});
```

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC node --test tests/js/seasons.test.mjs`
Expected: FAIL at load (`Cannot read properties of undefined` on `FH_SEASON_TOOLS`).

- [ ] **Step 3: Implement**

In `theme.js`, replace the existing `inWindow` and `seasonFor` and `nextSeason` with date-aware versions, add the helpers and export the tools:

1. Above `inWindow` (inside the seasonal section) add:
```javascript
  // ---- dates for moving holidays: pure, year-based ----
  // nthWeekday: the day of month of the nth `weekday` (0 = Sunday) of `month` (1-12) in `year`.
  function nthWeekday(year, month, weekday, n) {
    var first = new Date(year, month - 1, 1).getDay();
    return 1 + ((weekday - first + 7) % 7) + (n - 1) * 7;
  }
  // Easter Sunday (the Gregorian computus, Meeus/Jones/Butcher): [month, day].
  function easterSunday(year) {
    var a = year % 19, b = Math.floor(year / 100), c = year % 100;
    var d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
    var g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
    var i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
    var m = Math.floor((a + 11 * h + 22 * l) / 451);
    return [Math.floor((h + l - 7 * m + 114) / 31), ((h + l - 7 * m + 114) % 31) + 1];
  }
  // [month, day] of (year, month, day) shifted by n days
  function shiftDay(year, month, day, n) {
    var t = new Date(year, month - 1, day + n);
    return [t.getMonth() + 1, t.getDate()];
  }
  // The named windows a season can use as `window: WINDOWS.easter`. Each takes the year.
  var WINDOWS = {
    easter: function (y) { var e = easterSunday(y); return { from: shiftDay(y, e[0], e[1], -14), to: shiftDay(y, e[0], e[1], 1) }; },
    mothersDay: function (y) { var s = nthWeekday(y, 5, 0, 2); return { from: shiftDay(y, 5, s, -6), to: [5, s] }; },
    fathersDay: function (y) { var s = nthWeekday(y, 6, 0, 3); return { from: shiftDay(y, 6, s, -3), to: [6, s] }; },
    mlkDay: function (y) { var m = nthWeekday(y, 1, 1, 3); return { from: shiftDay(y, 1, m, -3), to: [1, m] }; },
    thanksgiving: function (y) { var t = nthWeekday(y, 11, 4, 4); return { from: shiftDay(y, 11, t, -10), to: shiftDay(y, 11, t, 3) }; }
  };
  // A season's window for a year: a moving one computes it, a fixed one is its from/to.
  function windowOf(season, year) {
    return typeof season.window === "function" ? season.window(year) : { from: season.from, to: season.to };
  }
```
2. Replace `inWindow` with:
```javascript
  // month*100+day compares calendar dates without a year; a window whose start
  // is later than its end wraps the new year.
  function inWindow(season, date) {
    var md = (date.getMonth() + 1) * 100 + date.getDate();
    var w = windowOf(season, date.getFullYear());
    var from = w.from[0] * 100 + w.from[1];
    var to = w.to[0] * 100 + w.to[1];
    return from <= to ? (md >= from && md <= to) : (md >= from || md <= to);
  }
```
3. Replace `seasonFor(date)` with `function seasonFor(date, list) { list = list || SEASONS; for (...) if (inWindow(list[i], date)) return list[i]; return null; }`.
4. Add `seasonOutlook` after `seasonFor`:
```javascript
  // When a season next opens after `date` (a Date): this year's start if still ahead, else next year's.
  function nextStart(season, date) {
    var y = date.getFullYear();
    for (var k = 0; k < 2; k++) {
      var w = windowOf(season, y + k);
      var start = new Date(y + k, w.from[0] - 1, w.from[1]);
      if (start > date) return start;
    }
    var w2 = windowOf(season, y + 2);
    return new Date(y + 2, w2.from[0] - 1, w2.from[1]);
  }
  // The picker's three groups: seasons whose window holds `date`, the next three to open (soonest
  // first), and everything else (registry order). Each season is in exactly one group.
  function seasonOutlook(date, list) {
    list = list || SEASONS;
    var active = [], waiting = [];
    for (var i = 0; i < list.length; i++) {
      if (inWindow(list[i], date)) active.push(list[i]);
      else waiting.push({ season: list[i], at: nextStart(list[i], date), i: i });
    }
    waiting.sort(function (a, b) { return a.at - b.at || a.i - b.i; });
    var upcoming = waiting.slice(0, 3).map(function (w) { return w.season; });
    var rest = list.filter(function (s) { return active.indexOf(s) === -1 && upcoming.indexOf(s) === -1; });
    return { active: active, upcoming: upcoming, rest: rest };
  }
```
5. Rewrite `window.nextSeason` to use `nextStart`:
```javascript
  window.nextSeason = function (date) {
    var d = isDate(date) ? date : new Date();
    var best = null, bestAt = null;
    for (var i = 0; i < SEASONS.length; i++) {
      var at = nextStart(SEASONS[i], d);
      if (bestAt === null || at < bestAt) { bestAt = at; best = SEASONS[i]; }
    }
    return best;
  };
```
6. Export, next to `window.FH_SEASONS = SEASONS;`:
```javascript
  window.FH_SEASON_TOOLS = {
    nthWeekday: nthWeekday, easterSunday: easterSunday, windows: WINDOWS, windowOf: windowOf,
    inWindow: inWindow, seasonFor: seasonFor, seasonOutlook: seasonOutlook
  };
  window.seasonOutlook = function (date) { return seasonOutlook(isDate(date) ? date : new Date()); };
```
Update the comment above `SEASONS` to document the new optional fields (`window`, `when`, `drift`).

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC node --test tests/js/seasons.test.mjs` then `TZ=UTC node --test tests/js/*.test.mjs`
Expected: all pass (the existing `nextSeason`/`activeSeason` tests included; if one asserted the old md-gap ordering, rule on the smallest change that keeps its meaning and ledger it).

- [ ] **Step 5: Mutation-check**

(a) off-by-one in `nthWeekday`, (b) `easterSunday` day +1, (c) Easter window `-13`, (d) `inWindow` ignoring `window`, (e) seasonOutlook not sorting, (f) Thanksgiving `+4`. Each fails a test. Restore and `cmp`.

- [ ] **Step 6: Commit**

CHANGELOG `### Added`: `- Seasons: the registry can now hold holidays that move each year (Easter, Mother's Day, Father's Day, MLK Day, Thanksgiving), with the date maths and the whole-calendar overlap rules tested; nothing visible changes yet.`

```bash
git add src/family_hub/web/static/theme.js tests/js/seasons.test.mjs CHANGELOG.md
git commit -m "feat: moving-date season windows, recipes and the picker outlook"
```

---

### Task 2: `drift` and `when` in the registry; `data-drift`

**Files:**
- Modify: `src/family_hub/web/static/theme.js`, `tests/js/seasons.test.mjs`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `refreshLook`, `SEASONS` (Task 1).
- Produces: `<html data-drift="none|snow|petal|clover|firefly|sparkle">` stamped by `refreshLook` from the painting season's `drift` (unknown or missing -> `none`; no look -> `none`); `window.FH_DRIFTS`.

- [ ] **Step 1: Write the failing tests** (append to `tests/js/seasons.test.mjs`)

`refreshLook` reads the real `SEASONS`, so test it through a loader that can inject a registry. Extend `loadTools` to accept `{ now, seasons }`: when `seasons` is given, the test replaces the registry by evaluating theme.js with `SEASONS` swapped: simplest, export `window.FH_SEASONS` (it IS the array) and mutate it in place in the test (`win.FH_SEASONS.push({...})`), then call `win.refreshLook(date)`.

```javascript
function loadTheme({ now } = {}) {
  const attrs = {};
  const root = { setAttribute(k, v) { attrs[k] = String(v); }, getAttribute(k) { return k in attrs ? attrs[k] : null; } };
  const store = new Map([['fh.season', 'on']]);
  const win = { localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) } };
  const sandbox = { window: win, document: { documentElement: root } };
  vm.createContext(sandbox);
  vm.runInContext(themeSrc, sandbox);
  return { win, root };
}

test('data-drift follows the painting season: its kind, else none', () => {
  const { win, root } = loadTheme();
  win.FH_SEASONS.unshift({ id: 'winter', name: 'Winter', from: [12, 1], to: [2, 29], drift: 'snow',
    looks: [{ id: 'winter-test', name: 'T', blurb: '', default: true }] });
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-look'), 'winter-test');
  assert.equal(root.getAttribute('data-drift'), 'snow');
  win.refreshLook(new Date(2026, 9, 6));                       // Halloween: no drift declared
  assert.equal(root.getAttribute('data-drift'), 'none');
  win.refreshLook(new Date(2026, 6, 15));                      // nothing in season
  assert.equal(root.getAttribute('data-look'), 'none');
  assert.equal(root.getAttribute('data-drift'), 'none');
});

test('an unknown drift kind reads as none; every known kind is accepted', () => {
  const { win, root } = loadTheme();
  for (const kind of ['snow', 'petal', 'clover', 'firefly', 'sparkle']) {
    win.FH_SEASONS.unshift({ id: 'x', name: 'X', from: [12, 1], to: [12, 31], drift: kind, looks: [{ id: 'x-a', name: 'A', blurb: '', default: true }] });
    win.refreshLook(new Date(2026, 11, 10));
    assert.equal(root.getAttribute('data-drift'), kind, kind);
    win.FH_SEASONS.shift();
  }
  win.FH_SEASONS.unshift({ id: 'x', name: 'X', from: [12, 1], to: [12, 31], drift: 'confetti', looks: [{ id: 'x-a', name: 'A', blurb: '', default: true }] });
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'none');
  assert.deepEqual(Array.from(win.FH_DRIFTS), ['snow', 'petal', 'clover', 'firefly', 'sparkle']);
});

test('turning seasons off clears the drift with the look', () => {
  const { win, root } = loadTheme();
  win.FH_SEASONS.unshift({ id: 'x', name: 'X', from: [12, 1], to: [12, 31], drift: 'snow', looks: [{ id: 'x-a', name: 'A', blurb: '', default: true }] });
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'snow');
  win.setSeason('off');
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'none');
});
```

- [ ] **Step 2: Run to verify RED** (`TZ=UTC node --test tests/js/seasons.test.mjs`): the three new tests FAIL (`data-drift` is `null`).

- [ ] **Step 3: Implement**

In `theme.js`: after `var SEASON_PREFS = ...` add `var DRIFTS = ["snow", "petal", "clover", "firefly", "sparkle"];`. In `refreshLook`, after the `data-look` write add:
```javascript
    var drift = season && DRIFTS.indexOf(season.drift) !== -1 ? season.drift : "none";
    if (root.getAttribute("data-drift") !== drift) root.setAttribute("data-drift", drift);
```
Export `window.FH_DRIFTS = DRIFTS;`. Add `data-drift  none | snow | petal | clover | firefly | sparkle  (DERIVED from the painting season's registry drift)` to the header comment's attribute list.

- [ ] **Step 4: Run to verify GREEN** (`TZ=UTC node --test tests/js/*.test.mjs`).
- [ ] **Step 5: Mutation-check:** (a) drop the known-kind check, (b) stamp the drift without the season check (stale after look none), (c) never clear to `none`. Each fails a test; restore and `cmp`.
- [ ] **Step 6: Commit** (CHANGELOG `### Added`: `- Seasons: each season can name one gentle kind of motion (snow, petals, clover leaves, fireflies or sparkle); the page records which in data-drift. Nothing paints it yet.`)

```bash
git add src/family_hub/web/static/theme.js tests/js/seasons.test.mjs CHANGELOG.md
git commit -m "feat: seasons carry a drift kind, stamped as data-drift"
```

---

### Task 3: The Settings picker groups its seasons

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (`seasonWindowText`, `seasonalCardHtml`, the "nothing in season" note in `reflectThemeControls`), `src/family_hub/web/static/styles.css`, `tests/js/hub-dom.test.mjs`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `seasonOutlook()` (Task 1), `FH_SEASONS`, `activeSeason()`, `nextSeason()`, season `when` text.
- Produces: the card renders three groups, each season exactly once: **In season now** (a `<div class="look-group">`, open), **Coming up** and **More seasons** (`<details class="look-group look-fold">` with a `<summary>`, closed). The painting season keeps its "In season" badge. `seasonWindowText(s)` returns `s.when` for a moving season, else "Oct 1 to Oct 31"; the "starts ..." note for a moving season says `starts ` + the lower-cased `when`.

- [ ] **Step 1: Write the failing tests** in `tests/js/hub-dom.test.mjs`. Extend `seasonHub()`'s stubs with `seasonOutlook: () => ({ active: [FALL[0]], upcoming: [], rest: [] })` and, for the new tests, a richer fixture:

```javascript
const WIN = { id: 'winter', name: 'Winter', from: [12, 1], to: [2, 29], looks: [{ id: 'winter-a', name: 'Frost', blurb: 'B', default: true }] };
const EAS = { id: 'easter', name: 'Easter', when: 'About two weeks before Easter Sunday', looks: [{ id: 'easter-a', name: 'Pastel', blurb: 'B', default: true }] };
const SPR = { id: 'spring', name: 'Spring', from: [3, 1], to: [5, 31], looks: [{ id: 'spring-a', name: 'Bloom', blurb: 'B', default: true }] };

function groupedHub(outlook) {
  const env = seasonHub();
  Object.assign(env.sandbox, { FH_SEASONS: [FALL[0], WIN, EAS, SPR], seasonOutlook: () => outlook });
  const host = env.document.createElement('div');
  host._id = 'settings-full';
  env.document.body.appendChild(host);
  env.sandbox.renderSettingsFull();
  return { ...env, host, html: host.innerHTML };
}

test('the Seasonal looks picker groups its seasons: in season open, the rest folded', () => {
  const { html } = groupedHub({ active: [FALL[0]], upcoming: [WIN, EAS], rest: [SPR] });
  assert.match(html, /<div class="look-group"[^>]*>[\s\S]*?In season now/);
  assert.match(html, /<details class="look-group look-fold"><summary>Coming up<\/summary>/);
  assert.match(html, /<details class="look-group look-fold"><summary>More seasons<\/summary>/);
  assert.doesNotMatch(html, /<details[^>]*\bopen\b/, 'folded groups start closed');
});

test('every season appears exactly once across the groups, whatever the outlook says', () => {
  const { html } = groupedHub({ active: [FALL[0]], upcoming: [WIN, EAS], rest: [SPR] });
  for (const id of ['fall-harvest', 'winter-a', 'easter-a', 'spring-a']) {
    assert.equal((html.match(new RegExp(`data-look-pick="${id}"`, 'g')) || []).length, 1, id);
  }
});

test('an empty group is not drawn; a moving season shows its when text, a fixed one its dates', () => {
  const none = groupedHub({ active: [], upcoming: [WIN, EAS], rest: [] });
  assert.doesNotMatch(none.html, /In season now/);
  assert.doesNotMatch(none.html, /More seasons/);
  assert.match(none.html, /About two weeks before Easter Sunday/);
  assert.match(none.html, /Dec 1 to Feb 29/);
});

test('the in-season season keeps its badge; picking a look inside a folded group still sets it', () => {
  const { html, host, calls, fire } = groupedHub({ active: [FALL[0]], upcoming: [WIN], rest: [] });
  assert.match(html, /In season/);
  const btn = host.querySelector('[data-look-pick="winter-a"]');
  btn.closest = (s) => (s === '.theme-ctl [data-look-pick]' || s === '[data-look-pick]' ? btn : null);
  fire('click', { target: btn, preventDefault() {} });
  assert.ok(calls.some((c) => c[0] === 'setSeasonLook' && c[1] === 'winter-a'));
});

test('with nothing in season the note says when the next one starts, moving ones in words', () => {
  const env = seasonHub();
  Object.assign(env.sandbox, { activeSeason: () => null, nextSeason: () => EAS });
  env.document.documentElement.setAttribute('data-season', 'on');
  const host = env.document.createElement('div');
  host._id = 'settings-full';
  env.document.body.appendChild(host);
  env.sandbox.renderSettingsFull();
  env.sandbox.reflectThemeControls();
  const note = env.document.querySelectorAll('.season-idle-note')[0];
  assert.match(note.textContent, /Easter starts about two weeks before Easter Sunday/);
});
```

(Adapt the click selector to the real handler used for tiles: read the existing `data-look-pick` click branch in `hub.js` and use the same `closest` string the neighbouring tile tests use. Update the existing "a Seasonal looks card ... a preview tile per look" test only where it asserts exact `<div>` counts or the old flat structure.)

- [ ] **Step 2: Run to verify RED** (`TZ=UTC node --test --test-name-pattern="picker|exactly once|empty group|in-season season|nothing in season" tests/js/hub-dom.test.mjs`): the new tests FAIL.

- [ ] **Step 3: Implement**

In `hub.js`:
```javascript
function seasonWindowText(s) {
  if (s.when) return s.when;
  const md = ([m, d]) => `${MONTHS[m - 1]} ${d}`;
  return `${md(s.from)} to ${md(s.to)}`;
}
// "starts Sep 1" / "starts about two weeks before Easter Sunday"
function seasonStartText(s) {
  return s.when ? s.when.charAt(0).toLowerCase() + s.when.slice(1) : seasonWindowText(s).split(' to ')[0];
}
```
In `reflectThemeControls` replace `upcoming.name} starts ${seasonWindowText(upcoming).split(' to ')[0]}.` with `${upcoming.name} starts ${seasonStartText(upcoming)}.`.

In `seasonalCardHtml`, keep the `tile` and the per-season `group` builders but render three groups from `seasonOutlook()`:
```javascript
  const outlook = typeof seasonOutlook === 'function' ? seasonOutlook() : { active: seasonList(), upcoming: [], rest: [] };
  const block = (s) => '<div class="look-season">' /* the existing per-season markup, unchanged */ + '</div>';
  const section = (title, list, fold) => !list.length ? ''
    : (fold
      ? `<details class="look-group look-fold"><summary>${title}</summary>${list.map(block).join('')}</details>`
      : `<div class="look-group"><div class="look-group-title">${title}</div>${list.map(block).join('')}</div>`);
  const groups = section('In season now', outlook.active, false)
    + section('Coming up', outlook.upcoming, true)
    + section('More seasons', outlook.rest, true);
```
(`block` is the existing `seasonList().map((s) => ...)` body, with `seasonWindowText(s)` for the "when" label.) The `In season` badge stays tied to `s.id === now`.

In `styles.css` add rules for `.look-group`, `.look-group-title`, `.look-fold`, `.look-fold > summary` (quiet small-caps headings in the existing Settings type scale, a 44px tap target for the summary on the phone, a visible focus ring, the native marker kept or replaced by a `::before` chevron that does not animate) next to the other `.look-season` rules. No transitions or animations.

- [ ] **Step 4: Run to verify GREEN:** `TZ=UTC node --test tests/js/*.test.mjs` and `<venv>/python -m pytest tests/test_static.py -q` (the class guard must pass: `look-group`, `look-group-title`, `look-fold` are styled).
- [ ] **Step 5: Mutation-check:** (a) draw empty groups, (b) render a season in two groups, (c) open the folded groups by default, (d) drop the badge, (e) use the dates text for a moving season. Each fails a test.
- [ ] **Step 6: Browser check** (demo, headless Edge): the Settings page at 1920 and 390 with the real two seasons (Halloween and Fall both in season) and with a forced fixture (`FH_SEASONS` pushed with Winter/Easter/Spring and `seasonOutlook` overridden) showing all three groups; tap targets 44px on the phone; keyboard focus on a summary. Read the images.
- [ ] **Step 7: Commit** (CHANGELOG `### Changed`: `- Settings > Seasonal looks groups its seasons (in season now, coming up, more seasons) so the list stays short as seasons are added.`)

```bash
git add src/family_hub/web/static/hub.js src/family_hub/web/static/styles.css tests/js/hub-dom.test.mjs CHANGELOG.md
git commit -m "feat: Settings groups seasons into in season, coming up and more"
```

---

### Task 4: The generic drift layer (snow, petals, clover, fireflies, sparkle)

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (a `seasonDriftHtml` builder, `seasonFxHtml`, `seasonSceneHtml`, tile `data-drift`), `src/family_hub/web/static/styles.css`, `tests/test_static.py`, `tests/js/hub-dom.test.mjs`, `CHANGELOG.md`
- Create: `src/family_hub/web/static/seasons/shape-petal.svg`, `shape-clover.svg`, `shape-spark.svg`; append rows to `src/family_hub/web/static/seasons/CREDITS.md`

**Interfaces:**
- Consumes: `data-drift` on `<html>` (Task 2) and `data-drift` on a Settings tile's `.look-swatch` (from the season's registry `drift`); the layers `body > .season` (far) and `body > .season-fx` (near) that Lite hides; `--sn-k`.
- Produces: markup `<span class="sn-drift front|back"><span class="sn-bit"><b></b></span> x10</span>` inside both layers; CSS that shows it only for a known `data-drift`, with per-kind shape, size, speed and motion; the guard entries.

- [ ] **Step 1: Write the failing tests**

`tests/js/hub-dom.test.mjs`:
```javascript
test('seasonDriftHtml: one layer of ten bits, bare spans, safe inside a tile <button>', () => {
  const { sandbox } = newHub();
  const html = sandbox.seasonDriftHtml('front');
  assert.match(html, /^<span class="sn-drift front">/);
  assert.equal((html.match(/<span class="sn-bit"><b><\/b><\/span>/g) || []).length, 10);
  assert.doesNotMatch(html, /<div/);
  assert.equal((html.match(/<span\b/g) || []).length, (html.match(/<\/span>/g) || []).length);
});

test('both season layers and a Settings preview carry the drift layer', () => {
  const { sandbox } = newHub();
  assert.match(sandbox.seasonFxHtml('back'), /sn-drift back/);
  assert.match(sandbox.seasonFxHtml(), /sn-drift front/);
  assert.match(sandbox.seasonSceneHtml(), /sn-drift/);
});

test('a Settings tile carries its season\'s drift kind so the preview can rest it', () => {
  const env = seasonHub();
  Object.assign(env.sandbox, { FH_SEASONS: [{ id: 'winter', name: 'Winter', from: [12, 1], to: [2, 29], drift: 'snow',
    looks: [{ id: 'winter-a', name: 'Frost', blurb: 'B', default: true }] }], seasonOutlook: () => ({ active: [], upcoming: [], rest: [] }) });
  env.sandbox.seasonOutlook = () => ({ active: [env.sandbox.FH_SEASONS[0]], upcoming: [], rest: [] });
  const host = env.document.createElement('div');
  host._id = 'settings-full';
  env.document.body.appendChild(host);
  env.sandbox.renderSettingsFull();
  assert.match(host.innerHTML, /class="look-swatch" data-look="winter-a" data-drift="snow"/);
});
```

`tests/test_static.py` (append):
```python
DRIFT_KINDS = ("snow", "petal", "clover", "firefly", "sparkle")


def test_every_drift_kind_has_its_shape_motion_and_a_resting_preview():
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for kind in DRIFT_KINDS:
        assert re.search(rf'data-drift="{kind}"\]?[^{{]*\.sn-bit[^{{]*\{{', css), f"{kind} styles its bits"
        assert re.search(rf'\.look-swatch\[data-drift="{kind}"\][^{{]*\.sn-bit[^{{]*\{{[^}}]*animation:\s*none', css), \
            f"{kind} rests in a Settings preview"
    # shown only for a known kind, never by default
    assert re.search(r"\.sn-drift\s*\{[^}]*display:\s*none", css), "the drift layer is hidden by default"
    for shape in ("shape-petal.svg", "shape-clover.svg", "shape-spark.svg"):
        assert (STATIC / "seasons" / shape).exists(), shape


def test_drift_motion_is_compositor_only_and_stops_for_reduced_motion_and_night():
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for sel, body in re.findall(r"([^{}]*\.sn-bit[^{}]*)\{([^}]*)\}", css):
        for prop in re.findall(r"([a-z-]+)\s*:", body):
            assert prop not in ("left", "top", "width", "height", "margin", "box-shadow", "filter") or "animation" not in body, \
                f"{sel.strip()} animates a layout/paint property"
    reduced = css[css.index("prefers-reduced-motion: reduce"):]
    assert ".sn-bit" in reduced and re.search(r"\.sn-bit[^{]*\{[^}]*animation:\s*none", reduced), "reduced motion stops the bits"
    assert re.search(r"\.is-night[^{]*\.sn-bit[^{]*\{[^}]*animation-play-state:\s*paused", css), "night pauses the far bits"
```
Also add `"sn-drift"` and `"sn-bit"` to `LITE_COVERS` in the Lite guard section and run `test_every_moving_season_part_is_known_to_lite...` (it must fail until the CSS exists and pass after).

- [ ] **Step 2: Run to verify RED** (the new tests FAIL; no `seasonDriftHtml`, no CSS).

- [ ] **Step 3: Implement**

`hub.js`:
```javascript
// The new seasons' one gentle kind of motion (snow, petals, clover leaves, fireflies, sparkle):
// ten bare bits whose shape, size, speed and colour come from styles.css, keyed on <html>'s
// data-drift (the wall) or the tile's own data-drift (Settings). One generic layer, so a season
// is registered with `drift: "snow"` and styled with tokens, never with its own markup.
function seasonDriftHtml(depth = 'front') {
  const bit = '<span class="sn-bit"><b></b></span>';
  return `<span class="sn-drift ${depth}">${bit.repeat(10)}</span>`;
}
```
`seasonFxHtml` returns `seasonLeavesHtml(depth) + seasonHauntHtml(depth) + seasonDriftHtml(depth)`; `seasonSceneHtml` includes `seasonDriftHtml()` after the leaves. In `seasonalCardHtml`'s `tile`, emit the swatch as `<span class="look-swatch" data-look="${id}"${s.drift ? ` data-drift="${escapeHtml(s.drift)}"` : ''} aria-hidden="true">` (so `tile` takes the season: change `tile = (look) =>` to `tile = (look, drift) =>` and call `s.looks.map((l) => tile(l, s.drift))`; the attribute string must be built in a helper so the class guard does not read it as a class).

Create the three shape SVGs (abstract, one colour, `viewBox="0 0 100 100"`, simple paths you author: a petal = a pointed ellipse, a clover leaf = four rounded hearts around a centre, a spark = a four-pointed star) and add three `CREDITS.md` rows (`self-made, CC0`).

`styles.css`, in the seasonal section before the Lite block (so Lite and reduced-motion, which come later, win):
- `.sn-drift { display: none; position: absolute; inset: 0; }`; show it: `:root[data-drift]:not([data-drift="none"]) body > .season-fx .sn-drift, ...body > .season .sn-drift { display: block; }` and, for previews, `.look-swatch[data-drift] .sn-drift { display: block; }`.
- `.sn-bit { position: absolute; left: var(--x); top: var(--y); width: var(--s); height: var(--s); }`, `.sn-bit b { display: block; width: 100%; height: 100%; opacity: var(--o, 1); }`, and ten `nth-child` placement rules (x, y, size, duration, delay, drift, amplitude) for the front layer, ten for `.sn-drift.back` (smaller, slower, no shadow), the same way the leaves do it.
- Per kind (selector `:root[data-drift="K"] .sn-bit` for the wall, `.look-swatch[data-drift="K"] .sn-bit` resting for previews with `animation: none; top: var(--y);` and the inner `b` too):
  - **snow:** `b` is a soft round flake (`radial-gradient`), sizes 3 to 9px (x `var(--sn-k, 1)`), fall `sn-fall` 18 to 40s linear with `sn-sway` on the inner `b`.
  - **petal:** `b` masked with `shape-petal.svg`, colour from `--sn-bit-1/--sn-bit-2` (default blush), 12 to 22px, fall + sway + the existing `sn-rock` tumble, 24 to 46s.
  - **clover:** `b` masked with `shape-clover.svg`, green tokens, 14 to 26px, fall + sway 26 to 48s.
  - **firefly:** `b` a small glowing dot (`radial-gradient`, no `filter`), 5 to 8px, NO fall: a slow `sn-wander` (translate3d loop) plus `sn-glow` (opacity pulse), 9 to 16s, placed over the lower two thirds.
  - **sparkle:** `b` masked with `shape-spark.svg`, 5 to 12px, no travel: `sn-twinkle` (opacity and a small scale) 3 to 7s with staggered delays.
- New keyframes `sn-wander`, `sn-glow`, `sn-twinkle` use only `transform` and `opacity`. `sn-fall`, `sn-sway`, `sn-rock` are reused.
- Colour tokens default to white/blush/green/gold per kind and may be overridden by a look's accent block later (a look sets only photo, focal point, bit colours and accent).
- Night: add `.is-night .sn-bit, .is-night .sn-bit b { animation-play-state: paused; }` next to the leaf/bat night rule (the near layer is already hidden at night).
- Reduced motion: add `.sn-bit, .sn-bit b { animation: none; }` and `.sn-drift` rest positions to the existing `prefers-reduced-motion` block's exact-selector list (the existing guard `test_reduced_motion_stops_every_seasonal_animation_by_its_exact_selector` fails until you do).
- Phone: size through `var(--sn-k, 1)`; the phone block's existing `--sn-k` halving applies automatically.

- [ ] **Step 4: Run to verify GREEN:** `TZ=UTC node --test tests/js/*.test.mjs` and `<venv>/python -m pytest tests/test_static.py -q` (every guard: class styling, Lite coverage with `sn-drift`/`sn-bit`, CREDITS rows, reduced motion, "every season surface hidden by default").

- [ ] **Step 5: Browser check (demo)**: with no season registered nothing changes anywhere (seasons off and Halloween/Fall screenshots equal main outside animated panels and the clock). Then force each kind on a wall: `document.documentElement.setAttribute('data-look', 'fall-aspen-grove'); document.documentElement.setAttribute('data-drift', '<kind>')` and screenshot 1920x1080 in Grey and Light: the bits are visible, small, slow, not over text in a distracting way, correct shape and colour; both depths read; with `setLite('on')` they never show; with `is-night` they rest; reduced motion (CDP `Emulation.setEmulatedMedia`) rests them; the phone at 390 shrinks them; a Settings tile for a forced `data-drift` rests. Read every image; tune values by eye (this is where the numbers get settled) and add a test for anything you change that was wrong.

- [ ] **Step 6: Mutation-check:** (a) animate `left` in a keyframe, (b) drop the reduced-motion rule, (c) drop `sn-bit` from `LITE_COVERS`, (d) show `.sn-drift` by default, (e) drop a kind's resting preview, (f) drop the tile `data-drift`. Each fails a test; restore and `cmp`.

- [ ] **Step 7: Commit** (CHANGELOG `### Added`: `- Seasons: a generic gentle-motion layer (snow, petals, clover leaves, fireflies, sparkle) for the seasons coming next; it is hidden by Lite, stops for reduced motion and at night, and nothing paints it yet.`)

```bash
git add src/family_hub/web/static/hub.js src/family_hub/web/static/styles.css src/family_hub/web/static/seasons tests/js/hub-dom.test.mjs tests/test_static.py CHANGELOG.md
git commit -m "feat: generic drift layer for snow, petals, clover, fireflies and sparkle"
```

---

### Task 5: The free-photo search helper

**Files:**
- Create: `scripts/season-photo-search.py`, `tests/test_season_photo_search.py`
- Modify: `docs/seasonal-looks.md` (a "Finding photos" section), `CHANGELOG.md`

**Interfaces:**
- Produces: `python scripts/season-photo-search.py search "snow covered pine forest" --out DIR [--sources commons,met,aic] [--min-width 2560] [--limit 24]` writing `DIR/contact-sheet.html` (thumbnails, title, creator, licence, size, link to the source page) and `DIR/candidates.json`; `fetch SOURCE:ID --out FILE` downloading one original on request and printing a draft `CREDITS.md` row. Stdlib only; dev-only like `prep-season-photo.py`.
- Pure, testable functions: `is_free(licence: str) -> bool`, `keep(c, min_width, landscape=True) -> bool`, `parse_commons(payload: dict) -> list[dict]`, `sheet_html(cands: list[dict]) -> str`.

- [ ] **Step 1: Write the failing tests** (`tests/test_season_photo_search.py`):

```python
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("sps", Path(__file__).resolve().parents[1] / "scripts" / "season-photo-search.py")
sps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sps)


def test_only_public_domain_and_cc0_are_free():
    for ok in ("Public domain", "CC0", "CC0 1.0", "PD US Government", "PD-USGov-NPS", "Public domain (NASA)"):
        assert sps.is_free(ok), ok
    for bad in ("CC BY 4.0", "CC BY-SA 2.0", "CC BY-NC 4.0", "Unsplash License", "Pexels License", "", None, "All rights reserved", "Free to use"):
        assert not sps.is_free(bad), bad


def test_keep_wants_a_big_landscape_free_image():
    good = {"licence": "Public domain", "width": 4500, "height": 3000}
    assert sps.keep(good, 2560)
    assert not sps.keep({**good, "width": 1900}, 2560), "too small for the wall"
    assert not sps.keep({**good, "width": 3000, "height": 4500}, 2560), "portrait"
    assert not sps.keep({**good, "licence": "CC BY-SA 2.0"}, 2560), "not free"
    assert sps.keep({**good, "width": None}, 2560, allow_unknown_size=True)
    assert not sps.keep({**good, "width": None}, 2560)


COMMONS = {"query": {"pages": {"1": {"index": 1, "title": "File:Snow-covered pine forest (52599268392).jpg", "imageinfo": [{
    "url": "https://upload.example/orig.jpg", "thumburl": "https://upload.example/thumb.jpg", "width": 4500, "height": 3000,
    "descriptionurl": "https://commons.example/File:Snow",
    "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "Artist": {"value": "<a href=\"x\">A. Photographer</a>"}}}]}}}}


def test_parse_commons_extracts_a_candidate_with_a_plain_creator():
    [c] = sps.parse_commons(COMMONS)
    assert c["source"] == "commons" and c["licence"] == "Public domain" and c["width"] == 4500
    assert c["creator"] == "A. Photographer", "markup stripped"
    assert c["page"].startswith("https://commons.") and c["thumb"].endswith("thumb.jpg")


def test_the_contact_sheet_escapes_everything_it_prints():
    html = sps.sheet_html([{"source": "commons", "id": "1", "title": "<script>x</script>", "creator": "\"><b>", "licence": "CC0",
                            "width": 4000, "height": 2000, "thumb": "https://t/x.jpg", "page": "https://p/x"}])
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>" not in html
    assert "CC0" in html and "4000" in html and "https://p/x" in html


def test_the_helper_never_touches_the_network_at_import_or_in_pure_functions(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    sps.is_free("CC0"); sps.keep({"licence": "CC0", "width": 3000, "height": 1500}, 2560); sps.parse_commons(COMMONS)
```

- [ ] **Step 2: Run to verify RED** (`<venv>/python -m pytest tests/test_season_photo_search.py -q`): FAIL (script missing).

- [ ] **Step 3: Implement** `scripts/season-photo-search.py`:

```python
#!/usr/bin/env python3
"""Search open sources for seasonal-look photo candidates (dev-only, stdlib only).

    python scripts/season-photo-search.py search "snow covered pine forest" --out scratch/winter [--min-width 2560]
    python scripts/season-photo-search.py fetch commons:File:Snow-covered_pine_forest_(52599268392).jpg --out scratch/winter/pick.jpg

Only sources that satisfy docs/seasonal-looks.md section 5 are searched: Wikimedia Commons (public domain and
CC0 files, which includes NPS and NASA works), The Met open access and the Art Institute of Chicago (both
filtered to public domain). The current Unsplash, Pexels and Pixabay licences are NOT used (operator decision
2026-10-06). `search` writes contact-sheet.html and candidates.json; nothing is downloaded until `fetch`.
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "family-hub-photo-search/0.1 (dev tool; public-domain search)"}
FREE = re.compile(r"^(cc0\b|public domain\b|pd[ -])", re.I)


def is_free(licence):
    return bool(licence) and bool(FREE.match(str(licence).strip()))


def keep(c, min_width, landscape=True, allow_unknown_size=False):
    if not is_free(c.get("licence")):
        return False
    w, h = c.get("width"), c.get("height")
    if not w or not h:
        return allow_unknown_size
    if w < min_width:
        return False
    return (w >= h * 1.3) if landscape else True


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_commons(payload):
    out = []
    pages = (payload.get("query") or {}).get("pages") or {}
    for pg in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (pg.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata") or {}
        out.append({"source": "commons", "id": pg["title"], "title": pg["title"].removeprefix("File:"),
                    "creator": _plain((meta.get("Artist") or {}).get("value")) or "unknown",
                    "licence": (meta.get("LicenseShortName") or {}).get("value"),
                    "width": info.get("width"), "height": info.get("height"),
                    "thumb": info.get("thumburl"), "page": info.get("descriptionurl"), "original": info.get("url")})
    return out


def search_commons(query, limit):
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query + " filetype:bitmap",
         "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo", "iiprop": "url|size|extmetadata",
         "iiurlwidth": "480", "iiextmetadatafilter": "LicenseShortName|Artist"}
    return parse_commons(_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))


def search_met(query, limit):
    ids = (_get("https://collectionapi.metmuseum.org/public/collection/v1/search?"
                + urllib.parse.urlencode({"q": query, "hasImages": "true", "isPublicDomain": "true"})).get("objectIDs") or [])[:limit]
    out = []
    for oid in ids:
        o = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        if o.get("isPublicDomain") and o.get("primaryImage"):
            out.append({"source": "met", "id": str(oid), "title": o.get("title", ""), "creator": o.get("artistDisplayName") or "unknown",
                        "licence": "Public domain (Met open access, CC0)", "width": None, "height": None,
                        "thumb": o.get("primaryImageSmall"), "page": o.get("objectURL"), "original": o["primaryImage"]})
    return out


def search_aic(query, limit):
    d = _get("https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(
        {"q": query, "limit": str(limit), "fields": "id,title,artist_display,image_id,is_public_domain,thumbnail",
         "query[term][is_public_domain]": "true"}))
    out = []
    for a in d.get("data", []):
        if a.get("is_public_domain") and a.get("image_id"):
            iiif = f"https://www.artic.edu/iiif/2/{a['image_id']}"
            th = a.get("thumbnail") or {}
            out.append({"source": "aic", "id": str(a["id"]), "title": a.get("title", ""), "creator": a.get("artist_display") or "unknown",
                        "licence": "Public domain (AIC, CC0)", "width": th.get("width"), "height": th.get("height"),
                        "thumb": f"{iiif}/full/400,/0/default.jpg", "page": f"https://www.artic.edu/artworks/{a['id']}",
                        "original": f"{iiif}/full/full/0/default.jpg"})
    return out


SOURCES = {"commons": search_commons, "met": search_met, "aic": search_aic}


def sheet_html(cands):
    e = html.escape
    cards = "".join(
        f'<figure><a href="{e(c["page"] or "", quote=True)}"><img src="{e(c["thumb"] or "", quote=True)}" alt=""></a>'
        f'<figcaption><b>{e(c["title"])}</b><br>{e(c["creator"])}<br>{e(str(c["licence"]))} &middot; '
        f'{e(str(c["width"] or "?"))} x {e(str(c["height"] or "?"))}<br><code>{e(c["source"])}:{e(c["id"])}</code></figcaption></figure>'
        for c in cands)
    return ("<!doctype html><meta charset=utf-8><title>Season photo candidates</title><style>"
            "body{font:14px system-ui;background:#111;color:#ddd;margin:16px}"
            "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}"
            "figure{margin:0}img{width:100%;aspect-ratio:16/9;object-fit:cover;background:#222}"
            "figcaption{padding:6px 0}a{color:#9cf}</style><main>" + cards + "</main>")


def cmd_search(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    found = []
    for name in a.sources.split(","):
        try:
            found += SOURCES[name](a.query, a.limit)
        except Exception as ex:                       # one source being down must not lose the others
            print(f"{name}: {type(ex).__name__}: {ex}", file=sys.stderr)
    kept = [c for c in found if keep(c, a.min_width, allow_unknown_size=a.allow_unknown_size)]
    (out / "candidates.json").write_text(json.dumps(kept, indent=2))
    (out / "contact-sheet.html").write_text(sheet_html(kept), encoding="utf-8")
    print(f"{len(found)} found, {len(kept)} kept (free licence, landscape, >= {a.min_width}px) -> {out / 'contact-sheet.html'}")


def cmd_fetch(a):
    source, _, ident = a.ref.partition(":")
    cand = next((c for c in json.loads((Path(a.out).parent / "candidates.json").read_text())
                 if c["source"] == source and c["id"] == ident), None)
    if not cand:
        sys.exit("not in candidates.json next to --out (run search first)")
    urllib.request.urlretrieve(cand["original"], a.out)
    print(f"saved {a.out}\nCREDITS.md row:\n| {Path(a.out).name} | {cand['title']} by {cand['creator']} | {cand['page']} | {cand['licence']} | resized to 2560px, metadata stripped |")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--out", required=True)
    s.add_argument("--sources", default="commons,met,aic")
    s.add_argument("--min-width", type=int, default=2560)
    s.add_argument("--limit", type=int, default=24)
    s.add_argument("--allow-unknown-size", action="store_true", help="keep art results whose size the API does not give")
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fetch")
    f.add_argument("ref", help="SOURCE:ID exactly as shown on the contact sheet")
    f.add_argument("--out", required=True)
    f.set_defaults(fn=cmd_fetch)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify GREEN** (`<venv>/python -m pytest tests/test_season_photo_search.py -q`), then the full static + house-data tests.

- [ ] **Step 5: Real run (not committed):** `python scripts/season-photo-search.py search "snow covered forest" --out <scratchpad>/winter-demo` on this PC (network), open the contact sheet, and confirm: only public-domain/CC0 rows, thumbnails load, sizes shown, the HTML escapes. Show the operator the path to `contact-sheet.html`. Fix anything the real data breaks (a field missing, a thumbnail host refusing the referrer) with a test.

- [ ] **Step 6: Docs and commit.** `docs/seasonal-looks.md`: a "Finding photos" section after section 5: what the helper searches and why Unsplash/Pexels are not searched (the operator's 2026-10-06 decision to keep the rule), the two commands, "pick from the contact sheet, then `fetch`, then `prep-season-photo.py`, then the CREDITS row", and the reminder to judge by eye behind the glass. CHANGELOG `### Added`: `- Docs/dev: scripts/season-photo-search.py finds public-domain and CC0 photo candidates (Wikimedia Commons, the Met, the Art Institute of Chicago) and writes a contact sheet for choosing seasonal looks.`

```bash
git add scripts/season-photo-search.py tests/test_season_photo_search.py docs/seasonal-looks.md CHANGELOG.md
git commit -m "feat: free-photo search helper and contact sheet for seasonal looks"
```

---

### Task 6: Docs, full verification, review, PR

- [ ] **Step 1: Docs.** `docs/seasonal-looks.md` section 6 and 7: how a season is now registered (`window: WINDOWS.<name>` or `from`/`to`, `when`, `drift`, order rules, the `data-drift` stamp, that a season's motion needs no per-season CSS, only `drift` plus colour tokens), and the registry-order rule with the overlaps the whole-calendar test pins. README: one line under Seasonal looks that the picker groups seasons. CHANGELOG `### Added` bullet: `- Docs: the seasonal-looks standard describes moving windows, the drift kinds and the registry order for the seasons coming next.`
- [ ] **Step 2: Full suites and visual regression.** `TZ=UTC node --test tests/js/*.test.mjs`; the full pytest (only the 49 known Windows failures); the demo: seasons off, Fall and Halloween walls unchanged vs main (outside the animated panels and the clock), Lite still hides everything, the Settings page grouped at 1920 and 390.
- [ ] **Step 3: Review.** A fresh-context review of the whole branch with this plan's Review Focus verbatim; apply Critical/Important in ONE fix pass (each fix RED then GREEN); ledger minors.
- [ ] **Step 4: Push and PR** with `gh pr create -R dapperdodger/family-hub --base main --head feat/seasons-groundwork` (plain `gh pr create` resolves to the wrong owner); body ends with the attribution line from the session reminder.
- [ ] **Step 5: Hand-off for PR 2.** With the operator, run `season-photo-search.py` for Winter, Spring and Summer and review the contact sheets together before writing PR 2's plan (it has its own plan and spec section).
