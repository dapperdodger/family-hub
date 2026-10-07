// Executable tests for the season date machinery in theme.js (moving holiday windows, the
// whole-calendar season table, the picker's outlook, the drift kind). theme.js is loaded into a vm
// sandbox like theme.test.mjs does; no network, no storage beyond a stub.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const staticDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'src', 'family_hub', 'web', 'static');
const themeSrc = readFileSync(join(staticDir, 'theme.js'), 'utf8');

function loadTheme() {
  const attrs = {};
  const root = { setAttribute(k, v) { attrs[k] = String(v); }, getAttribute(k) { return k in attrs ? attrs[k] : null; } };
  const store = new Map([['fh.season', 'on']]);
  const win = { localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) } };
  const sandbox = { window: win, document: { documentElement: root } };
  vm.createContext(sandbox);
  vm.runInContext(themeSrc, sandbox);
  return { win, root };
}
const T = loadTheme().win.FH_SEASON_TOOLS;
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
  { id: 'newyears', from: [12, 27], to: [1, 2] },
  { id: 'christmas', from: [12, 1], to: [12, 26] },
  { id: 'mlkday', window: (y) => T.windows.mlkDay(y) },
  { id: 'valentines', from: [2, 1], to: [2, 14] },
  { id: 'winter', from: [12, 1], to: [2, 29] },
  { id: 'stpatricks', from: [3, 1], to: [3, 17] },
  { id: 'easter', window: (y) => T.windows.easter(y) },
  { id: 'mothersday', window: (y) => T.windows.mothersDay(y) },
  { id: 'spring', from: [3, 1], to: [5, 31] },
  { id: 'fathersday', window: (y) => T.windows.fathersDay(y) },
  { id: 'julyfourth', from: [6, 25], to: [7, 4] },
  { id: 'summer', from: [6, 1], to: [8, 31] },
  { id: 'halloween', from: [10, 1], to: [10, 31] },
  { id: 'thanksgiving', window: (y) => T.windows.thanksgiving(y) },
  { id: 'fall', from: [9, 1], to: [11, 30] },
];
const on = (s) => { const r = T.seasonFor(d(s), PLAN); return r ? r.id : null; };

test('the whole-calendar table: every window edge, every overlap, the leap day, New Year', () => {
  const table = {
    '2026-12-27': 'newyears', '2027-01-01': 'newyears', '2027-01-02': 'newyears', '2027-01-03': 'winter',
    '2027-01-14': 'winter', '2027-01-15': 'mlkday', '2027-01-18': 'mlkday', '2027-01-19': 'winter',
    '2026-12-01': 'christmas', '2026-12-26': 'christmas', '2026-12-31': 'newyears',
    '2027-02-01': 'valentines', '2027-02-14': 'valentines', '2027-02-15': 'winter', '2028-02-29': 'winter',
    '2026-03-01': 'stpatricks', '2026-03-17': 'stpatricks', '2026-03-21': 'spring',
    '2026-03-22': 'easter', '2026-04-06': 'easter', '2026-04-07': 'spring',
    '2024-03-17': 'stpatricks', '2024-03-18': 'easter', '2024-04-01': 'easter',
    '2026-05-03': 'spring', '2026-05-04': 'mothersday', '2026-05-10': 'mothersday', '2026-05-11': 'spring',
    '2026-05-31': 'spring', '2026-06-01': 'summer', '2026-06-11': 'summer',
    '2026-06-17': 'summer', '2026-06-18': 'fathersday', '2026-06-21': 'fathersday', '2025-06-12': 'fathersday', '2025-06-15': 'fathersday',
    '2026-06-22': 'summer', '2026-06-25': 'julyfourth', '2026-07-04': 'julyfourth', '2026-07-05': 'summer', '2026-08-31': 'summer',
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
  assert.equal(T.seasonFor(d('2026-07-15')).id, 'summer', 'July is Summer now that the broad seasons are in');
});

test('seasonOutlook groups the picker: what is in season, what comes next by date, the rest', () => {
  const fixture = [
    { id: 'a', from: [10, 1], to: [10, 31] }, { id: 'b', from: [9, 1], to: [11, 30] },
    { id: 'easter', window: (y) => T.windows.easter(y) }, { id: 'c', from: [12, 1], to: [12, 26] },
    { id: 'e', from: [2, 1], to: [2, 14] }, { id: 'f', from: [6, 12], to: [6, 19] },
  ];
  const o = T.seasonOutlook(d('2026-10-06'), fixture);
  assert.deepEqual(Array.from(o.active.map((s) => s.id)), ['a', 'b'], 'both windows hold today, registry order');
  assert.deepEqual(Array.from(o.upcoming.map((s) => s.id)), ['c', 'e', 'easter'], 'the next three to start, soonest first');
  assert.deepEqual(Array.from(o.rest.map((s) => s.id)), ['f'], 'everything else, registry order');
});

test('seasonOutlook with nothing in season lists the next ones; a moving window is found next year', () => {
  const fixture = [{ id: 'easter', window: (y) => T.windows.easter(y) }, { id: 'c', from: [12, 1], to: [12, 26] }];
  const o = T.seasonOutlook(d('2026-04-20'), fixture);   // Easter 2026 has passed: next is Dec 1, then Easter 2027
  assert.deepEqual(Array.from(o.active), []);
  assert.deepEqual(Array.from(o.upcoming.map((s) => s.id)), ['c', 'easter']);
});

test('nextStart: this year\'s start when it is still ahead, else next year\'s, else a year after for a moving one', () => {
  const feb = { from: [2, 1], to: [2, 14] };
  assert.equal(T.nextStart(feb, d('2026-10-06')).toDateString(), d('2027-02-01').toDateString(), 'rolls into next year');
  assert.equal(T.nextStart(feb, d('2026-01-10')).toDateString(), d('2026-02-01').toDateString(), 'still ahead this year');
  assert.equal(T.nextStart(feb, d('2026-02-01')).toDateString(), d('2027-02-01').toDateString(), 'a window opening today is already open');
  const easter = { window: (y) => T.windows.easter(y) };
  assert.equal(T.nextStart(easter, d('2026-04-20')).toDateString(), d('2027-03-14').toDateString(), 'Easter 2027 Mar 28 minus 14 days');
});

// ---- drift: a season names one gentle kind of motion; <html data-drift> follows the painting season

const seasonOf = (drift, extra = {}) => ({ id: 'x', name: 'X', from: [12, 1], to: [12, 31], drift,
  looks: [{ id: 'x-a', name: 'A', blurb: '', default: true }], ...extra });

test('data-drift follows the painting season: its kind, else none', () => {
  const { win, root } = loadTheme();
  win.refreshLook(new Date(2026, 0, 15));                      // Jan 15: Winter
  assert.equal(root.getAttribute('data-look'), 'winter-mthood');
  assert.equal(root.getAttribute('data-drift'), 'snow');
  win.refreshLook(new Date(2026, 11, 10));                     // Dec 10: Christmas owns December
  assert.equal(root.getAttribute('data-look'), 'christmas-santa');
  assert.equal(root.getAttribute('data-drift'), 'snow');
  win.refreshLook(new Date(2026, 3, 10));
  assert.equal(root.getAttribute('data-drift'), 'petal');
  win.refreshLook(new Date(2026, 6, 15));
  assert.equal(root.getAttribute('data-drift'), 'firefly');
  win.refreshLook(new Date(2026, 9, 6));                       // Halloween: no drift declared
  assert.equal(root.getAttribute('data-drift'), 'none');
  win.FH_SEASONS.splice(0);                                    // nothing in season
  win.refreshLook(new Date(2026, 6, 15));
  assert.equal(root.getAttribute('data-look'), 'none');
  assert.equal(root.getAttribute('data-drift'), 'none');
});

test('an unknown drift kind reads as none; every known kind is accepted', () => {
  const { win, root } = loadTheme();
  for (const kind of ['snow', 'petal', 'clover', 'firefly', 'sparkle']) {
    win.FH_SEASONS.unshift(seasonOf(kind));
    win.refreshLook(new Date(2026, 11, 10));
    assert.equal(root.getAttribute('data-drift'), kind, kind);
    win.FH_SEASONS.shift();
  }
  win.FH_SEASONS.unshift(seasonOf('confetti'));
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'none');
  assert.deepEqual(Array.from(win.FH_DRIFTS), ['snow', 'petal', 'clover', 'firefly', 'sparkle']);
});

test('turning seasons off clears the drift with the look', () => {
  const { win, root } = loadTheme();
  win.FH_SEASONS.unshift(seasonOf('snow'));
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'snow');
  win.setSeason('off');
  win.refreshLook(new Date(2026, 11, 10));
  assert.equal(root.getAttribute('data-drift'), 'none');
});

test('a fresh page stamps data-drift none (no season painting yet)', () => {
  const { root } = loadTheme();
  assert.equal(root.getAttribute('data-drift'), 'none');
});


// ---- the registry itself must be able to USE the moving windows (review fix: WINDOWS was defined after it)

function loadFrom(src) {
  const attrs = {};
  const root = { setAttribute(k, v) { attrs[k] = String(v); }, getAttribute(k) { return k in attrs ? attrs[k] : null; } };
  const store = new Map([['fh.season', 'on']]);
  const win = { localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) } };
  const sandbox = { window: win, document: { documentElement: root } };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { win, root };
}

test('a season written as window: WINDOWS.easter in the registry loads and paints in its window', () => {
  const src = themeSrc.replace('var SEASONS = [', 'var SEASONS = [\n    { id: "eastertest", name: "Easter", when: "Around Easter", window: WINDOWS.easter, drift: "petal",'
    + ' looks: [{ id: "eastertest-a", name: "A", blurb: "b", default: true }] },');
  assert.notEqual(src, themeSrc, 'the registry marker is still there');
  const { win, root } = loadFrom(src);
  assert.equal(win.FH_SEASONS[0].id, 'eastertest');
  assert.equal(root.getAttribute('data-theme'), 'grey', 'the page was stamped (theme.js ran to the end)');
  assert.equal(win.refreshLook(new Date(2026, 3, 1)), 'eastertest-a');
  assert.equal(root.getAttribute('data-drift'), 'petal');
  assert.notEqual(win.refreshLook(new Date(2026, 3, 8)), 'eastertest-a', 'after Easter Monday it is over');
});

test('the date helpers and WINDOWS are defined before the registry that uses them', () => {
  assert.ok(themeSrc.indexOf('var WINDOWS = {') < themeSrc.indexOf('var SEASONS = ['), 'WINDOWS comes first');
  assert.ok(themeSrc.indexOf('function windowOf(') < themeSrc.indexOf('var SEASONS = ['));
});

const CAL = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'season-calendar.json'), 'utf8'));

test('the real registry: every edge of every window paints the season the calendar says', () => {
  assert.ok(CAL.length > 200, 'the fixture covers many edges');
  for (const [iso, want] of CAL) assert.equal(T.seasonFor(d(iso)).id, want, iso);
});

test('the real registry: no day of 2026 to 2028 is without a season', () => {
  for (const year of [2026, 2027, 2028]) {
    for (let t = new Date(year, 0, 1); t.getFullYear() === year; t = new Date(year, t.getMonth(), t.getDate() + 1)) {
      assert.ok(T.seasonFor(t), `${t.toDateString()} has a season`);
    }
  }
});

test('the real registry: October lists Halloween and Fall now, then the next three to start, then the rest', () => {
  const o = T.seasonOutlook(d('2026-10-06'));
  assert.deepEqual(Array.from(o.active.map((s) => s.id)), ['halloween', 'fall']);
  assert.deepEqual(Array.from(o.upcoming.map((s) => s.id)), ['thanksgiving', 'christmas', 'winter']);   // Winter also starts Dec 1; a tie goes to registry order
  assert.deepEqual(Array.from(o.rest.map((s) => s.id)),
    ['newyears', 'valentines', 'stpatricks', 'easter', 'mothersday', 'spring', 'fathersday', 'julyfourth', 'summer']);
});

test('the real registry: season and look ids, defaults, prefixes and the words moving seasons need', () => {
  const { win } = loadTheme();
  assert.deepEqual(Array.from(win.FH_SEASONS.map((s) => s.id)),
    ['newyears', 'christmas', 'valentines', 'winter', 'stpatricks', 'easter', 'mothersday', 'spring',
     'fathersday', 'julyfourth', 'summer', 'halloween', 'thanksgiving', 'fall']);
  const seen = new Set();
  for (const s of win.FH_SEASONS) {
    assert.equal(Array.from(s.looks).filter((l) => l.default).length, 1, `${s.id} has exactly one default look`);
    if (typeof s.window === 'function') assert.ok(s.when && s.when.length > 10, `${s.id} moves each year, so it needs a when text`);
    for (const l of s.looks) {
      assert.ok(l.id.startsWith(s.id + '-'), `${l.id} starts with ${s.id}-`);
      assert.ok(!seen.has(l.id), `${l.id} is unique`);
      seen.add(l.id);
    }
  }
  assert.equal(seen.size, 45);
  const counts = Object.fromEntries(win.FH_SEASONS.map((s) => [s.id, s.looks.length]));
  assert.deepEqual(counts, { newyears: 3, christmas: 3, valentines: 3, winter: 3, stpatricks: 3, easter: 3,
    mothersday: 3, spring: 3, fathersday: 3, julyfourth: 3, summer: 3, halloween: 5, thanksgiving: 4, fall: 3 });
  const drifts = Object.fromEntries(win.FH_SEASONS.map((s) => [s.id, s.drift || null]));
  assert.deepEqual(drifts, { newyears: 'sparkle', christmas: 'snow', valentines: 'petal', winter: 'snow',
    stpatricks: 'clover', easter: 'petal', mothersday: 'petal', spring: 'petal', fathersday: null, julyfourth: 'sparkle',
    summer: 'firefly', halloween: null, thanksgiving: null, fall: null });
});
