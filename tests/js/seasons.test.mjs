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
