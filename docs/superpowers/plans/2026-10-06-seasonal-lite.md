# Seasonal Lite Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-device Lite switch that keeps a seasonal photo on a slow screen (the wall's Pi 3) by dropping the glass blur and all the moving leaves, bats and spiders.

**Architecture:** `theme.js` stamps `data-lite="on|off"` on `<html>` like every other device preference (storage `fh.lite`, plus a `?lite=1`/`?lite=0` URL latch). One block of CSS keyed on that attribute swaps the glass blur for a plain 86% card fill, hides the motion layers and the photo's arrival fade. `hub.js` makes the JS-walked spiders stand down and adds a Lite row to Settings. A static guard makes any future season's animated class declare how Lite covers it.

**Tech Stack:** vanilla JS (`theme.js`, `hub.js`), CSS, node:test (vm sandbox + fake DOM), pytest static guards.

**Spec:** `docs/superpowers/specs/2026-10-06-seasonal-lite-design.md`

## Global Constraints

- Lite is per device: no house default, no automatic detection. Default `off`.
- With Lite on AND a look painting: wall glass = 86% of the theme's `--surface`, no `backdrop-filter`; the near layer (`body > .season-fx`), far leaves (`.season .sn-leaves`) and far bats (`.season .sn-bat`) never display; the photo's arrival fade is off. The webs and the season mark stay.
- Night keeps its own near-solid glass (94%) and wins over Lite. Settings preview tiles (`.look-swatch`, `.look-card`) are unchanged. With no look painting Lite changes nothing.
- The phone layout keeps its own rules; Lite only changes glass and motion.
- Never put `backdrop-filter` on a fixed/sticky element (unchanged). No new transitions/animations.
- Custom CSS classes must be styled (`test_every_referenced_class_is_styled`); the new Settings row reuses `.settings-row`, `.seg`, `.settings-sub`.
- Each src commit adds its own NEW "- " bullet under CHANGELOG `## [Unreleased]` (hook); no duplicate headings.
- The repo is public: no real IPs or tokens in docs or tests (`192.168.1.50` only).
- Run Python with the scratchpad venv, `TZ=UTC`, `PYTHONUTF8=1`; 49 Python tests fail identically on clean main on Windows (backup 30, install_hooks 13, caldav 2, google_client 2, check_changelog 1, api health 1). Write multi-line edit scripts to a file with the Write tool (the shell halves backslashes).

## Review Focus

- Lite on at night: the glass must stay at its 94% night fill, not drop to 86%.
- Lite on with seasons off or no season in the calendar: nothing visible changes (pixel-identical to Lite off).
- `?lite=1` when storage refuses writes: the attribute still stamps for this session; `?lite=0` clears it; junk like `?lite=2` or `?xlite=1` is ignored.
- Toggling Lite live (Settings tap) stops a spider mid-walk within its next beat and nothing keeps animating; toggling back resumes.
- The Settings preview tiles still show their small blurred glass card and still leaves.
- A future season that animates a new `.sn-*` class fails the guard until Lite covers it.

---

### Task 1: `theme.js` stamps `data-lite`

**Files:**
- Modify: `src/family_hub/web/static/theme.js`
- Modify: `tests/js/theme.test.mjs`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `<html data-lite="on|off">` stamped before first paint; `window.setLite(v)` (validates `on`/`off`, persists `fh.lite`, re-stamps); the URL latch `?lite=1`/`?lite=0`.

- [ ] **Step 1: Write the failing tests**

In `tests/js/theme.test.mjs`, extend `loadTheme` so a test can pass the page query and a storage that throws. Replace its signature and body start with:

```javascript
function loadTheme({ storage = {}, fhTheme, now, search, brokenStorage } = {}) {
  const root = makeRoot();
  const localStorage = brokenStorage
    ? { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } }
    : makeStorage(storage);
  const win = { localStorage };
  if (search !== undefined) win.location = { search };
  if (fhTheme !== undefined) win.FH_THEME = fhTheme;
```

(keep the rest of the function as it is.) Append these tests at the end of the file:

```javascript
// ---- Lite: data-lite (on | off), a per-device choice; ?lite=1 / ?lite=0 latches it

test('fresh device defaults to lite=off and persists nothing', () => {
  const { root, localStorage } = loadTheme();
  assert.equal(root.getAttribute('data-lite'), 'off');
  assert.equal(localStorage.getItem('fh.lite'), null);
});

test('setLite(on) stamps data-lite=on and persists; setLite(off) takes it back', () => {
  const { root, localStorage, win } = loadTheme();
  win.setLite('on');
  assert.equal(root.getAttribute('data-lite'), 'on');
  assert.equal(localStorage.getItem('fh.lite'), 'on');
  win.setLite('off');
  assert.equal(root.getAttribute('data-lite'), 'off');
  assert.equal(localStorage.getItem('fh.lite'), 'off');
});

test('an invalid lite value is rejected: no stamp change, no persist', () => {
  const { root, localStorage, win } = loadTheme();
  win.setLite('maybe');
  win.setLite(undefined);
  assert.equal(root.getAttribute('data-lite'), 'off');
  assert.equal(localStorage.getItem('fh.lite'), null);
});

test('a stored fh.lite=on survives a reload; a garbage stored value reads as off', () => {
  assert.equal(loadTheme({ storage: { 'fh.lite': 'on' } }).root.getAttribute('data-lite'), 'on');
  assert.equal(loadTheme({ storage: { 'fh.lite': 'banana' } }).root.getAttribute('data-lite'), 'off');
});

test('?lite=1 latches Lite on (and persists it), the way ?kiosk=1 latches the kiosk', () => {
  const first = loadTheme({ search: '?lite=1' });
  assert.equal(first.root.getAttribute('data-lite'), 'on');
  assert.equal(first.localStorage.getItem('fh.lite'), 'on');
  // a later load of the plain URL on the same device keeps it
  const again = loadTheme({ storage: { 'fh.lite': 'on' }, search: '' });
  assert.equal(again.root.getAttribute('data-lite'), 'on');
});

test('?lite=0 clears a latched Lite; the query may carry other parameters', () => {
  const off = loadTheme({ storage: { 'fh.lite': 'on' }, search: '?kiosk=1&lite=0' });
  assert.equal(off.root.getAttribute('data-lite'), 'off');
  assert.equal(off.localStorage.getItem('fh.lite'), 'off');
  assert.equal(loadTheme({ search: '?x=1&lite=1&y=2' }).root.getAttribute('data-lite'), 'on');
});

test('a junk ?lite value or a look-alike parameter is ignored', () => {
  for (const search of ['?lite=2', '?lite=', '?xlite=1', '?lite=on', '?litex=1']) {
    const { root, localStorage } = loadTheme({ search });
    assert.equal(root.getAttribute('data-lite'), 'off', search);
    assert.equal(localStorage.getItem('fh.lite'), null, search);
  }
});

test('with storage blocked, ?lite=1 still stamps this session and never throws', () => {
  const { root } = loadTheme({ brokenStorage: true, search: '?lite=1' });
  assert.equal(root.getAttribute('data-lite'), 'on');
  assert.equal(loadTheme({ brokenStorage: true }).root.getAttribute('data-lite'), 'off');
});

test('Lite is independent of the season choice and the house default', () => {
  const { root } = loadTheme({ storage: { 'fh.season': 'on' }, fhTheme: { season: 'on', lite: 'on' } });
  assert.equal(root.getAttribute('data-lite'), 'off', 'a house config never turns a device\'s Lite on');
});
```

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC node --test tests/js/theme.test.mjs`
Expected: the nine new tests FAIL (`data-lite` is `null`); the older tests still pass.

- [ ] **Step 3: Implement**

In `theme.js`:

1. In the header comment's attribute list, after the `data-look` entry, add:
```
     data-lite         on | off             (Lite: a slower screen keeps the seasonal
                                              photo, drops the glass blur and the moving
                                              leaves/bats/spiders; per device, no house default)
```
2. After `var IDLE_RETURNS = ["on", "off"];` add `var LITES = ["on", "off"];`, and after `var DEFAULT_IDLE_RETURN = "on";` add `var DEFAULT_LITE = "off";`.
3. After `stampIdleReturn` add:
```javascript
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
```
4. After `setIdleReturn` add:
```javascript
  function setLite(v) {
    if (LITES.indexOf(v) === -1) return;
    writeStored("fh.lite", v);
    stampLite(v);
  }
```
5. After `window.setIdleReturn = setIdleReturn;` add `window.setLite = setLite;`.
6. In the initial stamp block, after the `stampIdleReturn(...)` line and before `stampSeason(...)`, add:
```javascript
  var urlLite = liteFromUrl();
  if (urlLite) writeStored("fh.lite", urlLite);
  var storedLite = readStored("fh.lite");
  stampLite(urlLite || (LITES.indexOf(storedLite) !== -1 ? storedLite : DEFAULT_LITE));
```

- [ ] **Step 3b: Run to verify GREEN**

Run: `TZ=UTC node --test tests/js/theme.test.mjs` then `TZ=UTC node --test tests/js/*.test.mjs`
Expected: all pass.

- [ ] **Step 4: Mutation-check**

(a) drop the validation in `setLite`, (b) ignore the URL (`urlLite = null`), (c) make `?lite=0` not persist, (d) drop the `(?:&|$)` boundary in the regexp, (e) read the house default for Lite. Each must fail a test. Restore from a backup and `cmp`.

- [ ] **Step 5: Commit**

CHANGELOG `### Added` new bullet: `- Seasonal Lite: a per-device switch (stamped as data-lite, also latched by ?lite=1 in the page URL) for slower screens; the styles that use it follow.`

```bash
git add src/family_hub/web/static/theme.js tests/js/theme.test.mjs CHANGELOG.md
git commit -m "feat: theme.js stamps data-lite (per-device, ?lite=1 latch)"
```

---

### Task 2: The Lite CSS and its static guards

**Files:**
- Modify: `src/family_hub/web/static/styles.css` (a new block just BEFORE the "seasonal looks, reduced motion" block near the end)
- Modify: `tests/test_static.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `data-lite` (Task 1); the existing glass rules (`:where(:root[data-look]...) .card` etc.), `.season`, `.season-fx`, `.sn-leaves`, `.sn-bat`.
- Produces: the Lite behaviour; the guard `LITE_COVERS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_static.py` (check the top of the file for the existing `CSS`, `STATIC`, `re` names and reuse them):

```python
# ---------------------------------------------------------------- seasonal Lite

LITE_ON = r':root\[data-lite="on"\]\[data-look\]'


def _lite_blocks():
    """Every CSS rule whose selector starts with the Lite attribute pair, comments stripped."""
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]*" + LITE_ON + r"[^{}]*)\{([^}]*)\}", css)]


def test_lite_swaps_the_wall_glass_for_a_plain_fill_and_drops_the_blur():
    blocks = _lite_blocks()
    assert blocks, "a Lite block exists"
    fill = [b for sel, b in blocks if re.search(r"body:not\(\.is-night\)\s+\.wrap\b", sel) and "--glass" in b]
    assert fill and re.search(r"--glass:\s*color-mix\(in srgb,\s*var\(--surface\)\s*86%", fill[0]), \
        "the glass is 86% of the theme's own surface, set on .wrap and never at night"
    blur_sel = " ".join(sel for sel, b in blocks if re.search(r"backdrop-filter:\s*none", b))
    for target in (r"\.wrap \.card", r"\.wrap \.expand", r"\.wrap \.shead h2", r"\.topbar"):
        assert re.search(target, blur_sel), f"{target} loses its blur under Lite"
    assert not re.search(r"\.look-(swatch|card)", " ".join(sel for sel, _ in blocks)), \
        "the Settings preview tiles are not touched by Lite"


def test_lite_hides_every_moving_layer_and_the_arrival_fade():
    blocks = _lite_blocks()
    hidden = " ".join(sel for sel, b in blocks if re.search(r"display:\s*none", b))
    for layer in (r"body > \.season-fx", r"body > \.season \.sn-leaves", r"body > \.season \.sn-bat"):
        assert re.search(layer, hidden), f"{layer} never displays under Lite"
    still = " ".join(sel for sel, b in blocks if re.search(r"animation:\s*none", b))
    assert re.search(r"body > \.season\b(?! \.)", still), "the photo's arrival fade is off under Lite"
    assert "sn-web" not in hidden, "the webs never move and stay"


# every class a season ANIMATES must say how Lite covers it. Add the new class here (and to
# the Lite hide rule) when a season brings moving parts; the webs never move, so they are not listed.
LITE_COVERS = {
    "sn-leaves": r"body > \.season \.sn-leaves",   # the far/near leaf layers
    "sn-leaf": r"body > \.season \.sn-leaves",
    "sn-bat": r"body > \.season \.sn-bat",
    "sn-dangle": r"body > \.season-fx",            # the creatures walked from hub.js live in the near layer
    "sn-crawl": r"body > \.season-fx",
}


def test_every_class_a_season_animates_is_covered_by_lite():
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    animated = set()
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if re.search(r"animation(-name)?:\s*(?!none)", body) and "@keyframes" not in sel:
            animated.update(re.findall(r"\.(sn-[a-z-]+)", sel))
    hidden = " ".join(sel for sel, b in _lite_blocks() if re.search(r"display:\s*none", b))
    unknown = sorted(c for c in animated if c not in LITE_COVERS and c not in {"sn-haunt", "sn-near", "sn-far", "sn-front", "sn-back"})
    assert not unknown, f"these animated season classes are not covered by Lite (add them to LITE_COVERS and the Lite hide rule): {unknown}"
    for cls, layer in LITE_COVERS.items():
        assert re.search(layer, hidden), f"{cls}: Lite's hide rule {layer} is missing"
```

Adjust the allow-list of structural class names in the last test to whatever the first run reports as animated-but-structural (for example wrappers that only position children); anything that is a real moving shape must be in `LITE_COVERS`.

- [ ] **Step 2: Run to verify RED**

Run: `<venv>/python -m pytest tests/test_static.py -q -k lite`
Expected: FAIL (`a Lite block exists`).

- [ ] **Step 3: Implement**

In `styles.css`, immediately before the `/* ---- seasonal looks, reduced motion ----` comment, add:

```css
/* ---- seasonal Lite: a slower screen (the wall's Raspberry Pi 3) keeps the photo ----
   data-lite="on" (theme.js, per device). What the Pi cannot afford while a look paints: the glass
   blur (the browser re-samples the photo under every card whenever anything behind it repaints),
   the leaves and bats moving behind and over that glass, the JS-walked spiders. Lite keeps the
   photo, the season's colour and the still decorations (the webs, the season mark): the glass is
   86% of the theme's own card colour with no blur, the motion layers never display, and the photo
   no longer fades in. Night keeps its own near-solid glass (hence body:not(.is-night)). The
   Settings preview tiles are not selected here, so they still show the look in miniature. */
:root[data-lite="on"][data-look]:not([data-look="none"]) body:not(.is-night) .wrap {
  --glass: color-mix(in srgb, var(--surface) 86%, transparent);
}
:root[data-lite="on"][data-look]:not([data-look="none"]) .wrap .card,
:root[data-lite="on"][data-look]:not([data-look="none"]) .wrap .expand,
:root[data-lite="on"][data-look]:not([data-look="none"]) .wrap .shead h2,
:root[data-lite="on"][data-look]:not([data-look="none"]) .topbar {
  -webkit-backdrop-filter: none; backdrop-filter: none;
}
:root[data-lite="on"][data-look]:not([data-look="none"]) body > .season { animation: none; }
:root[data-lite="on"][data-look]:not([data-look="none"]) body > .season-fx,
:root[data-lite="on"][data-look]:not([data-look="none"]) body > .season .sn-leaves,
:root[data-lite="on"][data-look]:not([data-look="none"]) body > .season .sn-bat { display: none; }

```

- [ ] **Step 4: Run to verify GREEN**

Run: `<venv>/python -m pytest tests/test_static.py -q`
Expected: all pass, including `test_every_referenced_class_is_styled` and the existing season guards (`test_season_scene_sits_behind_and_never_takes_a_tap`, `test_every_season_surface_is_hidden_by_default`, `test_reduced_motion_stops_every_seasonal_animation_by_its_exact_selector`). If an existing guard objects to the new rules, rule on the smallest change and ledger it.

- [ ] **Step 5: Browser check (demo, headless Edge via `shot.mjs`)**

Start the demo and capture 1920x1080 for Grey, Light and Black with a Halloween look, `setLite('on')` vs off. Assert with `evalOut`: under Lite `getComputedStyle(card).backdropFilter === 'none'`, the `.season-fx` display is `none`, `body > .season .sn-leaves` display `none`; under Lite off the blur is present. Confirm at night (`document.body.classList.add('is-night')`) the card background alpha is the same with Lite on and off. Confirm the Settings tile preview still has `backdrop-filter: blur(10px)`. Seasons off (`setSeason('off')`): the page screenshot is byte-identical with Lite on and off. Read the images.

- [ ] **Step 6: Mutation-check**

(a) drop `body:not(.is-night)` from the fill rule (the night guard test or the browser night check must fail), (b) remove `.topbar` from the blur list, (c) remove the `.sn-bat` hide, (d) hide `.sn-web` too (the "webs stay" assertion), (e) add an animated `.sn-snow` rule (the future-season guard must fail with the helpful message). Each fails a guard. Restore and `cmp`.

- [ ] **Step 7: Commit**

CHANGELOG `### Added`: `- Seasonal Lite: with it on, a look keeps its photo but the glass is a plain 86% fill (no blur) and the leaves, bats and spiders never move or show; a test now fails if a new season animates something Lite does not cover.`

```bash
git add src/family_hub/web/static/styles.css tests/test_static.py CHANGELOG.md
git commit -m "feat: seasonal Lite CSS (no blur, no motion) and its guards"
```

---

### Task 3: The spiders stand down and Settings gets a Lite row

**Files:**
- Modify: `src/family_hub/web/static/hub.js`
- Modify: `tests/js/hub-dom.test.mjs`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `setLite` (Task 1), the existing `seasonalCardHtml`, `reflectThemeControls`, the `.theme-ctl` click handler, `snMotion(...).showing()`, `spiderStage`.
- Produces: `[data-lite-set="on|off"]` buttons in the Seasonal looks card; `showing()` false under Lite.

- [ ] **Step 1: Write the failing tests**

In `tests/js/hub-dom.test.mjs`:

1. In `spiderStage`, right after the line `document.documentElement.setAttribute('data-look', opts.look || 'halloween-two-lanterns');` add `if (opts.lite) document.documentElement.setAttribute('data-lite', 'on');`.
2. In the test `nothing to look at means nothing moves: no look painted, or a hidden tab`, extend the list to `[{ visible: false }, { look: 'none' }, { hiddenTab: true }, { lite: true }]` and update its comment line to mention Lite.
3. Add `setLite: (v) => calls.push(['setLite', v]),` to the `Object.assign` in `seasonHub()`.
4. Append:

```javascript
test('Lite stands a spider down before any layout question is asked', async () => {
  const { document, sandbox } = newHub();
  const { el } = spiderStage(sandbox, document, { lite: true });
  let asked = 0;
  el.checkVisibility = () => { asked += 1; return true; };
  const m = sandbox.snMotion(el);
  assert.equal(m.showing(), false);
  assert.equal(asked, 0, 'the attribute read answers first, so a Lite wall never pays for a layout read');
});

test('renderSettingsFull: the Seasonal looks card has a Lite row with an Off/On switch', () => {
  const { document, sandbox } = seasonHub();
  const host = document.createElement('div');
  host._id = 'settings-full';
  document.body.appendChild(host);
  sandbox.renderSettingsFull();
  const html = host.innerHTML;
  assert.match(html, /data-lite-set="off"/);
  assert.match(html, /data-lite-set="on"/);
  assert.match(html, /Lite[^<]*<|slower screen/i);
  assert.match(html, /Raspberry Pi 3/);
});

test('reflectThemeControls marks the Lite switch from data-lite (off when unstamped)', () => {
  const { document, sandbox } = seasonHub();
  const host = document.createElement('div');
  host._id = 'settings-full';
  document.body.appendChild(host);
  sandbox.renderSettingsFull();
  const marked = () => host.querySelectorAll('[data-lite-set]').filter((b) => b.classList.contains('on')).map((b) => b.dataset.liteSet);
  assert.deepEqual(marked(), ['off']);
  document.documentElement.setAttribute('data-lite', 'on');
  sandbox.reflectThemeControls();
  assert.deepEqual(marked(), ['on']);
});

test('tapping a Lite button calls setLite with that value and refreshes the switch', () => {
  const { document, sandbox, calls, fire } = seasonHub();
  const host = document.createElement('div');
  host._id = 'settings-full';
  document.body.appendChild(host);
  sandbox.renderSettingsFull();
  const btn = host.querySelector('[data-lite-set="on"]');
  btn.closest = (s) => (s === '.theme-ctl [data-lite-set]' ? btn : null);
  fire('click', { target: btn, preventDefault() {} });
  assert.deepEqual(calls.filter((c) => c[0] === 'setLite'), [['setLite', 'on']]);
});
```

If `seasonHub()` does not return `fire`, take it from the same `newHub()` result it wraps (`env.fire`) and return it. If the existing balanced-markup test counts `<div` / `<button>` totals only for balance (not exact numbers), it needs no change; if it asserts exact counts, update them by the Lite row's one extra div pair and two buttons and note why.

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC node --test --test-name-pattern="Lite|nothing to look at" tests/js/hub-dom.test.mjs`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

In `hub.js`:

1. In `snMotion`'s `showing()`, directly after `if (document.hidden) return false;` add:
```javascript
      // Lite: this screen cannot afford the creatures, and the CSS hides their layer; the
      // attribute is the cheap answer, asked before any layout question
      if (document.documentElement.getAttribute('data-lite') === 'on') return false;
```
2. In `seasonalCardHtml()`, after the `'<div class="season-idle-note" hidden></div>'` line and its closing `'</div>'` of the first row, add a second row so the return is:
```javascript
    + '<div class="season-idle-note" hidden></div>'
    + '</div>'
    + '<div class="settings-row">'
    + '<div class="seg" role="group" aria-label="Lite mode">'
    + '<button type="button" data-lite-set="off">Lite off</button>'
    + '<button type="button" data-lite-set="on">Lite on</button>'
    + '</div>'
    + '<div class="settings-sub">For a slower screen such as a Raspberry Pi 3: keeps the photo, drops the blur and the moving leaves, bats and spiders. This screen only.</div>'
    + '</div>'
    + `<div class="look-picker">${groups}</div>`;
```
(keep the `look-picker` line exactly once; only insert the new row before it.)
3. In `reflectThemeControls()`, after the `const season = ...` line add `const lite = el.getAttribute('data-lite') === 'on' ? 'on' : 'off';`, and inside the `.theme-ctl` loop after the `data-season-set` toggle add:
```javascript
    ctl.querySelectorAll('[data-lite-set]').forEach((b) =>
      b.classList.toggle('on', b.dataset.liteSet === lite));
```
4. In the click handler, right after the `data-season-set` branch (`const ss = ...; if (ss) {...}`), add:
```javascript
  const lt = e.target.closest('.theme-ctl [data-lite-set]');
  if (lt) { if (typeof setLite === 'function') setLite(lt.dataset.liteSet); reflectThemeControls(); return; }
```

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC node --test tests/js/*.test.mjs` and `<venv>/python -m pytest tests/test_static.py -q`
Expected: all pass.

- [ ] **Step 5: Mutation-check**

(a) remove the attribute check in `showing()` (the `asked === 0` test fails), (b) drop the reflect toggle, (c) drop the click branch, (d) swap `lite` default to `'on'` in reflect. Each fails a test. Restore and `cmp`.

- [ ] **Step 6: Commit**

CHANGELOG `### Added`: `- Settings > Seasonal looks has a Lite switch for this screen, and the Halloween spiders stand down under Lite without any layout work.`

```bash
git add src/family_hub/web/static/hub.js tests/js/hub-dom.test.mjs CHANGELOG.md
git commit -m "feat: Settings Lite switch; spiders stand down under Lite"
```

---

### Task 4: Docs and the visual gates

**Files:**
- Modify: `README.md`, `docs/seasonal-looks.md`, `CHANGELOG.md`
- (deploy repo, separate commit at the end) `pi-kiosk/README.md`

- [ ] **Step 1: Docs**

README (the Seasonal looks bullet): one paragraph: "**Lite** (Settings > Seasonal looks, per device, or add `?lite=1` to the screen's URL to latch it) keeps the photo but drops the blur and every moving leaf, bat and spider, for a slow screen such as a Raspberry Pi 3." `docs/seasonal-looks.md`: a new section "Lite mode and new seasons": what Lite removes, why the Pi 3 needs it, and the rule for every future season: moving parts go in the layers Lite hides (`body > .season-fx`, `.season .sn-leaves`, `.season .sn-bat`) or add their class to Lite's hide rule and to `LITE_COVERS` in `tests/test_static.py`; look at it with Lite on before calling a look done. CHANGELOG `### Added` bullet: `- Docs: the README and the seasonal-looks standard describe Lite and the rule new seasons follow.`

- [ ] **Step 2: Visual gates (demo, headless Edge)**

Capture and READ: each of Light, Soft, Blue, Grey, Black with a fall look and a Halloween look, Lite on and off (the photo visible between cards, text readable, empty check rings still visible, struck-through calendar lines still visible); night with Lite on; the phone at 390 with Lite on (no sideways spill, the gear popover above the cards); the Settings page with the new Lite row (both states) and a tile preview still showing its blurred glass card and still leaves; seasons off with Lite on vs main (byte-identical). Fix anything that fails the standard's "done" checklist, one test per fix.

- [ ] **Step 3: Full suites and commit**

Run `TZ=UTC node --test tests/js/*.test.mjs` and the full pytest (only the 49 known Windows failures remain).

```bash
git add README.md docs/seasonal-looks.md CHANGELOG.md
git commit -m "docs: Lite in the README and the seasonal-looks standard"
```

- [ ] **Step 4: Deploy repo (separate repo, its own commit; do not push without being asked)**

In `C:\Users\mrtim\Documents\family-hub-deploy\pi-kiosk\README.md` document that adding `&lite=1` to the kiosk URL latches Lite for the Pi (and `setup-kiosk.sh`'s `HUB_URL` default can be given with it). Do not change the script's default. Update `TODO.md` item 6 to say Lite is built and what still needs the operator (the Pi 3 readings).

---

### Task 5: Review, the Pi 3 readings and the PR

- [ ] **Step 1:** Run the review pass the repo asks for (`docs/adding-a-feature.md`): a fresh-context review of the whole branch with this plan's Review Focus verbatim; apply Critical/Important in ONE fix pass (each fix RED then GREEN, suite green); ledger the minors.
- [ ] **Step 2:** Push `feat/seasonal-lite` and open the PR with `gh pr create -R dapperdodger/family-hub --base main --head feat/seasonal-lite` (plain `gh pr create` resolves to the wrong owner). The body ends with the attribution line from the session reminder.
- [ ] **Step 3:** Ask the operator for the Pi 3 readings with Lite on (the same `top` / `vcgencmd` commands as the baselines) and record them in the deploy `TODO.md`.
