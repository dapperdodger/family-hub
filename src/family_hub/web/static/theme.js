/* ================================================================
   FAMILY HUB - theme.js

   Runs SYNCHRONOUSLY from <head>, before the body paints, so the wall
   never flashes the wrong theme (or the wrong layout). It reads the
   persisted preferences and stamps these attributes on <html>:

     data-theme        light | soft | dark | grey | black
     data-accent       cyan | violet | amber | green
     data-cols         none | wells | lines
     data-layout       auto | desktop       (the per-device layout CHOICE)
     data-idle-return  on | off             (per-device idle auto-return; hub.js
                                              reads it — behavioral, not visual)
     data-season       on | off             (seasonal looks follow the calendar)
     data-look         none | <look id>     (DERIVED from data-season + today's
                                              date; see SEASONS below)
     data-drift        none | snow | petal | clover | firefly | sparkle
                                             (DERIVED, like data-look: the painting season's
                                              registry `drift`, its one gentle kind of motion)
     data-lite         on | off             (Lite: a slower screen keeps the seasonal
                                              photo, drops the glass blur and the moving
                                              leaves/bats/spiders; per device, no house
                                              default; ?lite=1 / ?lite=0 in the URL latches it)

   data-layout is the ONLY layout attribute. In "auto" the phone/wall split
   is decided by a pure-CSS width media query (max-width:1000px) — no JS
   needed, so a phone still gets the mobile layout even if this script never
   runs. Choosing "desktop" forces the full wall at ANY width by suppressing
   that media query (the CSS keys the shell off :root:not([data-layout=
   "desktop"])); this is the escape hatch for a TV browser that mis-reports a
   phone-narrow width (e.g. a Fire TV) and would otherwise be stuck in the
   phone layout. Stamping data-layout before paint keeps the wall from
   flashing the phone shell first on such a device.

   Fallback order for each preference:
     1. localStorage  (fh.theme / fh.accent / fh.cols / fh.layout / fh.idleReturn
                       / fh.season): this device's own choice
     2. window.FH_THEME  { mode, accent, columns, layout, idleReturn, season }:
        the house default. hub.js sets it from each /api/hub poll, so it is
        only there after first paint (nothing injects it before this script
        runs); at startup it is normally undefined
     3. localStorage fh.house: the last house default hub.js handed to
        rememberHouseTheme, so a reload paints the house theme at once
        instead of grey-then-house (the next poll corrects a stale copy)
     4. hardcoded default  grey / green / none / auto / on / off

   Exposes setTheme / setAccent / setColumns / setLayout / setIdleReturn /
   setSeason (plus setSeasonLook, see the seasonal looks section): each
   validates its value, writes the localStorage key, and re-stamps live, so a
   control can apply a change without a reload.

   Dependency-free, no network, no house data. LAN wall display safe.
   ================================================================ */
(function () {
  "use strict";

  var root = document.documentElement;

  var THEMES = ["light", "soft", "dark", "grey", "black"];
  var ACCENTS = ["cyan", "violet", "amber", "green"];
  var COLUMNS = ["none", "wells", "lines"];
  var LAYOUTS = ["auto", "desktop"];
  var IDLE_RETURNS = ["on", "off"];
  var LITES = ["on", "off"];

  var DEFAULT_THEME = "grey";
  var DEFAULT_ACCENT = "green";
  var DEFAULT_COLUMNS = "none";
  var DEFAULT_LAYOUT = "auto";
  var DEFAULT_IDLE_RETURN = "on";
  var DEFAULT_LITE = "off";

  // localStorage can throw (private mode / disabled storage); never let that
  // break first paint.
  function readStored(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function writeStored(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      // Storage unavailable/locked-down (e.g. a kiosk TV WebView). The live
      // attribute still updates below, so the CURRENT session is correct — but
      // the choice won't survive a reload. Leave a breadcrumb so a
      // "my forced-Desktop TV reverted after reboot" report is diagnosable
      // rather than silent; never rethrow (that would break first paint).
      try { console.warn("family-hub: could not persist " + key + " (storage unavailable)"); } catch (e2) { /* no console */ }
    }
  }

  // The house default: window.FH_THEME when hub.js has set it (after a poll),
  // else the copy cached under fh.house by rememberHouseTheme below.
  var HOUSE_KEY = "fh.house";
  function cachedHouse() {
    var raw = readStored(HOUSE_KEY);
    if (!raw) return undefined;
    try {
      var v = JSON.parse(raw);
      return v && typeof v === "object" ? v : undefined;
    } catch (e) {
      return undefined;   // a corrupt copy is ignored; the next poll rewrites it
    }
  }
  function configDefault(field) {
    var cfg = window.FH_THEME;
    if (cfg && typeof cfg === "object" && cfg[field] !== undefined) return cfg[field];
    var house = cachedHouse();
    return house ? house[field] : undefined;
  }

  function resolve(allowed, storageKey, configField, hardDefault) {
    var stored = readStored(storageKey);
    if (allowed.indexOf(stored) !== -1) return stored;
    var cfg = configDefault(configField);
    if (allowed.indexOf(cfg) !== -1) return cfg;
    return hardDefault;
  }

  // Keep the house default for the next page load's first paint. Called by
  // hub.js with each /api/hub `theme`. This is NOT a device choice (those are
  // the fh.theme/... keys, which it never touches), so a later house change
  // still reaches every device that never chose. Storage failures are
  // swallowed: the cache only saves a flash, it must never break a poll.
  function rememberHouseTheme(theme) {
    if (!theme || typeof theme !== "object") return;
    var json;
    try { json = JSON.stringify(theme); } catch (e) { return; }
    if (readStored(HOUSE_KEY) === json) return;   // unchanged: skip the write
    try {
      window.localStorage.setItem(HOUSE_KEY, json);
    } catch (e) {
      // storage blocked: the next load paints grey first, as before
    }
  }
  window.rememberHouseTheme = rememberHouseTheme;

  function stampTheme(mode) {
    root.setAttribute("data-theme", mode);
  }
  function stampAccent(name) {
    root.setAttribute("data-accent", name);
  }
  function stampColumns(name) {
    root.setAttribute("data-cols", name);
  }

  // ---- layout: a single data-layout attribute (auto | desktop) ----
  // The CSS does the rest: a width media query handles "auto", and
  // :root:not([data-layout="desktop"]) lets "desktop" suppress the phone shell
  // at any width. No matchMedia and no computed "mode" — keeping the phone
  // layout a pure-CSS concern is what makes it survive this script not running.
  function stampLayout(layout) {
    root.setAttribute("data-layout", layout);
  }

  // ---- idle auto-return: data-idle-return (on | off) ----
  // Behavioral, not visual: hub.js's armIdle() reads this attribute and skips
  // arming the return-home timer when it is "off". Managed here (rather than ad
  // hoc in hub.js) so it shares the same localStorage + house-default + setter
  // machinery as the other device prefs. Default "on" keeps the shared wall's
  // existing drift-back-to-home behavior; a personal phone/TV sets "off".
  function stampIdleReturn(v) {
    root.setAttribute("data-idle-return", v);
  }

  // ---- Lite: data-lite (on | off) ----
  // A property of THIS screen (a Raspberry Pi 3 wall cannot afford the seasonal blur and
  // animation), so there is no house default. The CSS in styles.css keys off the attribute.
  function stampLite(v) {
    root.setAttribute("data-lite", v);
  }
  // ?lite=1 / ?lite=0 in the page URL latches the device choice, like osk.js's ?kiosk=1, so a
  // kiosk's start URL keeps it even if the browser profile is wiped. Anything else is ignored.
  function liteFromUrl() {
    var q = "";
    try { q = (window.location && window.location.search) || ""; } catch (e) { q = ""; }
    var m = /[?&]lite=([01])(?:&|$)/.exec(q);
    return m ? (m[1] === "1" ? "on" : "off") : null;
  }

  // ---- public setters: validate, persist, re-stamp live ----
  function setTheme(mode) {
    if (THEMES.indexOf(mode) === -1) return;
    writeStored("fh.theme", mode);
    stampTheme(mode);
  }
  function setAccent(name) {
    if (ACCENTS.indexOf(name) === -1) return;
    writeStored("fh.accent", name);
    stampAccent(name);
  }
  function setColumns(name) {
    if (COLUMNS.indexOf(name) === -1) return;
    writeStored("fh.cols", name);
    stampColumns(name);
  }
  function setLayout(layout) {
    if (LAYOUTS.indexOf(layout) === -1) return;
    writeStored("fh.layout", layout);
    stampLayout(layout);
  }
  function setIdleReturn(v) {
    if (IDLE_RETURNS.indexOf(v) === -1) return;
    writeStored("fh.idleReturn", v);
    stampIdleReturn(v);
  }
  function setLite(v) {
    if (LITES.indexOf(v) === -1) return;
    writeStored("fh.lite", v);
    stampLite(v);
  }

  window.setTheme = setTheme;
  window.setAccent = setAccent;
  window.setColumns = setColumns;
  window.setLayout = setLayout;
  window.setIdleReturn = setIdleReturn;
  window.setLite = setLite;

  // ---- stamp-only appliers: validate + re-stamp live, WITHOUT persisting ----
  // The house default from server config (window.FH_THEME / /api/hub) is applied
  // through these on a fresh device: it must change the LOOK without writing a
  // localStorage override (that key means "this device chose this"; writing the
  // house value there would freeze the device against future house-default
  // changes). Only the user's own control taps go through the setters above,
  // which do persist. See Task 5.
  function stampThemeIf(mode) {
    if (THEMES.indexOf(mode) !== -1) stampTheme(mode);
  }
  function stampAccentIf(name) {
    if (ACCENTS.indexOf(name) !== -1) stampAccent(name);
  }
  function stampColumnsIf(name) {
    if (COLUMNS.indexOf(name) !== -1) stampColumns(name);
  }
  function stampLayoutIf(layout) {
    if (LAYOUTS.indexOf(layout) !== -1) stampLayout(layout);
  }
  function stampIdleReturnIf(v) {
    if (IDLE_RETURNS.indexOf(v) !== -1) stampIdleReturn(v);
  }
  window.stampTheme = stampThemeIf;
  window.stampAccent = stampAccentIf;
  window.stampColumns = stampColumnsIf;
  window.stampLayout = stampLayoutIf;
  window.stampIdleReturn = stampIdleReturnIf;

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
  // ---- seasonal looks: data-season (the choice) + data-look (what paints) ----
  // A seasonal look is a real photograph (or public-domain artwork) filling
  // the screen behind glass cards, with a matching accent, leaves drifting
  // down and a small mark by the wordmark. It follows the calendar. The design
  // standards and sourcing rules live in docs/seasonal-looks.md; read that
  // before adding a look. Two prefs drive it:
  //   fh.season          on | off   (house default: FH_THEME.season)
  //   fh.look.<season>   which of that season's looks this device likes
  // and one derived attribute, data-look, names the look actually painted
  // ("none" when the season pref is off or today falls in no season).
  //
  // SEASONS is the one registry: the Settings tiles, the date windows and the
  // allowed look ids all come from it. To add a season, add an entry here, its
  // token blocks + scene rules in styles.css (test_static.py fails until every
  // look has them), and its art in static/seasons/ with a CREDITS.md line.
  // The server never sees look ids, only on/off. Order matters: the FIRST
  // season whose window holds today wins, so a short holiday (Halloween
  // inside fall, say) must be listed BEFORE the broad season it sits in. A
  // window may wrap the new year (from Dec 1 to Feb 28 works). Dates are
  // [month, day], both 1-based.
  var SEASONS = [
    // A season has a fixed window (`from`/`to`, month/day, inclusive, may wrap the year) OR a moving one
    // (`window: WINDOWS.easter`, a function of the year: see WINDOWS above), plus an optional `when` text
    // for Settings when it has no fixed dates ("About two weeks before Easter Sunday"). The first season
    // whose window holds today wins, so list a holiday BEFORE the broad season it sits in.
    // `default: true` marks the look a device gets before it picks one.
    // `credit` is shown on the Settings tile (full attribution lives in
    // static/seasons/CREDITS.md). Ids are storage keys and image file names:
    // renaming a look is free, changing its id resets that choice everywhere.
    { id: "halloween", name: "Halloween", from: [10, 1], to: [10, 31], looks: [
      { id: "halloween-two-lanterns", name: "Lantern Night", blurb: "Two carved pumpkins glowing in the dark", credit: "Photo by Beth Teutschmann", default: true },
      { id: "halloween-purple-sky", name: "Witching Hour", blurb: "The Milky Way over a violet horizon", credit: "Photo by Vincentiu Solomon" },
      { id: "halloween-purple-pines", name: "Haunted Pines", blurb: "Black pines against a purple night sky", credit: "Photo by Ryan Hutton" },
      { id: "halloween-moonrise", name: "Moonrise", blurb: "A full moon through the trees", credit: "Photo by the National Park Service" },
      { id: "halloween-branches", name: "Bare Branches", blurb: "A stand of bare trees at deep dusk", credit: "Photo by Vladimir Agafonkin" },
    ] },
    { id: "fall", name: "Fall", from: [9, 1], to: [11, 30], looks: [
      { id: "fall-aspen-grove", name: "Aspen Grove", blurb: "Sunlit gold under a blue sky", credit: "Photo by Patrick Myers, NPS", default: true },
      { id: "fall-misty-road", name: "Misty Road", blurb: "A quiet road through fog and fallen leaves", credit: "Photo by Bernd Schulz" },
      { id: "fall-maple-sky", name: "Maple Sky", blurb: "Red maple leaves against a clear blue sky", credit: "Photo by Aaron Burden" },
    ] },
  ];
  var SEASON_PREFS = ["on", "off"];
  // The gentle kinds of motion a season may name with `drift` (styles.css draws each one).
  var DRIFTS = ["snow", "petal", "clover", "firefly", "sparkle"];
  var DEFAULT_SEASON = "off";

  function seasonById(id) {
    for (var i = 0; i < SEASONS.length; i++) if (SEASONS[i].id === id) return SEASONS[i];
    return null;
  }
  function seasonOfLook(lookId) {
    for (var i = 0; i < SEASONS.length; i++) {
      var looks = SEASONS[i].looks;
      for (var j = 0; j < looks.length; j++) if (looks[j].id === lookId) return SEASONS[i];
    }
    return null;
  }
  // month*100+day compares calendar dates without a year; a window whose start
  // is later than its end wraps the new year.
  function inWindow(season, date) {
    var md = (date.getMonth() + 1) * 100 + date.getDate();
    var w = windowOf(season, date.getFullYear());
    var from = w.from[0] * 100 + w.from[1];
    var to = w.to[0] * 100 + w.to[1];
    return from <= to ? (md >= from && md <= to) : (md >= from || md <= to);
  }
  // duck-typed, not instanceof: a Date from another realm (an iframe, a test
  // sandbox) is still a Date
  function isDate(d) {
    return !!d && typeof d.getMonth === "function" && !isNaN(d.getTime());
  }
  function seasonFor(date, list) {
    list = list || SEASONS;
    for (var i = 0; i < list.length; i++) if (inWindow(list[i], date)) return list[i];
    return null;
  }
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
  // This session's picks, held in memory as well as storage: on a kiosk WebView
  // where setItem throws, a tap must still repaint now (the same "the CURRENT
  // session is correct" promise writeStored makes for every other pref).
  var lookPicks = {};
  // The look a season paints on this device: the device's favourite if it is
  // still one of the season's looks, else the season's default look (or its
  // first, if none is marked).
  function lookFor(season) {
    var fav = lookPicks[season.id] || readStored("fh.look." + season.id);
    for (var i = 0; i < season.looks.length; i++) if (season.looks[i].id === fav) return fav;
    for (var j = 0; j < season.looks.length; j++) if (season.looks[j].default) return season.looks[j].id;
    return season.looks[0].id;
  }

  function stampSeason(v) {
    root.setAttribute("data-season", v);
  }
  // Re-derive data-look from the season pref and the date. hub.js calls this on
  // its clock tick, so a wall left running rolls into (and out of) a season at
  // midnight with no reload. `date` is optional (tests pass a fixed one).
  function refreshLook(date) {
    var d = isDate(date) ? date : new Date();
    var season = root.getAttribute("data-season") === "on" ? seasonFor(d) : null;
    var look = season ? lookFor(season) : "none";
    if (root.getAttribute("data-look") !== look) root.setAttribute("data-look", look);
    var drift = season && DRIFTS.indexOf(season.drift) !== -1 ? season.drift : "none";
    if (root.getAttribute("data-drift") !== drift) root.setAttribute("data-drift", drift);
    return look;
  }
  // Did someone on THIS device choose the season pref this session? The house
  // default only applies to a device that never chose, and hub.js asks this
  // as well as localStorage, because on a kiosk where storage refuses writes
  // the next poll would otherwise stamp the house value over a fresh tap.
  var seasonChosen = false;
  function seasonChoiceMade() { return seasonChosen; }
  function setSeason(v) {
    if (SEASON_PREFS.indexOf(v) === -1) return;
    seasonChosen = true;
    writeStored("fh.season", v);
    stampSeason(v);
    refreshLook();
  }
  function stampSeasonIf(v) {
    if (SEASON_PREFS.indexOf(v) === -1) return;
    stampSeason(v);
    refreshLook();
  }
  // Remember a look as this device's favourite for ITS season. Choosing a look
  // is also a clear "I want seasonal looks", so it turns the season pref on AND
  // saves that as this device's own choice (even when a house default already
  // stamped "on": otherwise a later house change to "off" would undo the pick).
  // Out-of-season picks are kept and paint once their season comes round.
  function setSeasonLook(lookId) {
    var season = seasonOfLook(lookId);
    if (!season) return;
    lookPicks[season.id] = lookId;
    seasonChosen = true;
    writeStored("fh.look." + season.id, lookId);
    writeStored("fh.season", "on");
    stampSeason("on");
    refreshLook();
  }
  // The look a season would paint on this device right now (for the Settings
  // tiles' "selected" mark), and the season in force on a date (or null).
  function seasonLook(seasonId) {
    var season = seasonById(seasonId);
    return season ? lookFor(season) : null;
  }
  function activeSeason(date) {
    var s = seasonFor(isDate(date) ? date : new Date());
    return s ? s.id : null;
  }

  window.FH_SEASONS = SEASONS;
  window.FH_DRIFTS = DRIFTS;
  window.FH_SEASON_TOOLS = {
    nthWeekday: nthWeekday, easterSunday: easterSunday, windows: WINDOWS, windowOf: windowOf,
    inWindow: inWindow, seasonFor: seasonFor, seasonOutlook: seasonOutlook, nextStart: nextStart
  };
  window.seasonOutlook = function (date) { return seasonOutlook(isDate(date) ? date : new Date()); };
  window.setSeason = setSeason;
  window.stampSeason = stampSeasonIf;
  window.setSeasonLook = setSeasonLook;
  window.seasonChoiceMade = seasonChoiceMade;
  // The season whose window opens soonest after `date` (or null with no
  // seasons): lets the UI say "Fall starts Sep 1" when nothing is in season.
  window.nextSeason = function (date) {
    var d = isDate(date) ? date : new Date();
    var best = null, bestAt = null;
    for (var i = 0; i < SEASONS.length; i++) {
      var at = nextStart(SEASONS[i], d);
      if (bestAt === null || at < bestAt) { bestAt = at; best = SEASONS[i]; }
    }
    return best;
  };
  window.refreshLook = refreshLook;
  window.seasonLook = seasonLook;
  window.activeSeason = activeSeason;

  // ---- initial stamp (synchronous, before paint) ----
  stampTheme(resolve(THEMES, "fh.theme", "mode", DEFAULT_THEME));
  stampAccent(resolve(ACCENTS, "fh.accent", "accent", DEFAULT_ACCENT));
  stampColumns(resolve(COLUMNS, "fh.cols", "columns", DEFAULT_COLUMNS));
  stampLayout(resolve(LAYOUTS, "fh.layout", "layout", DEFAULT_LAYOUT));
  stampIdleReturn(resolve(IDLE_RETURNS, "fh.idleReturn", "idleReturn", DEFAULT_IDLE_RETURN));
  var urlLite = liteFromUrl();
  if (urlLite) writeStored("fh.lite", urlLite);
  var storedLite = readStored("fh.lite");
  stampLite(urlLite || (LITES.indexOf(storedLite) !== -1 ? storedLite : DEFAULT_LITE));
  stampSeason(resolve(SEASON_PREFS, "fh.season", "season", DEFAULT_SEASON));
  refreshLook();
})();
