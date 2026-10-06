# Seasonal Lite mode: design

TODO item 6. A per-device switch that keeps a seasonal photo on a slow screen (the wall's Raspberry Pi 3)
by dropping what costs it: the glass blur and the moving parts.

## Intent

The Pi 3 kiosk is smooth with seasons off and sluggish with a look painting (operator, 2026-10-06). The cost
is the 26px `backdrop-filter` blur on every card, section title, button and the top bar (the browser
re-samples the photo under each one whenever anything behind it repaints), the far leaves/bats animating
behind that glass, and the JS-walked Halloween spiders. **Lite keeps the photo and the season's colour, and
removes those costs.** Phones and fast screens are unchanged unless they turn Lite on.

## Decisions (operator, 2026-10-06)

- **How a device gets Lite:** a per-device switch (Settings > Seasonal looks, off by default) PLUS a `?lite=1`
  URL switch that latches it on, the way `?kiosk=1` works, so the Pi keeps it if its browser profile is
  wiped. `?lite=0` clears it. No automatic detection.
- **Motion:** all of it off in Lite (every leaf layer, bats, spiders). Still decorations stay (the corner
  webs, the season mark by the wordmark).
- **Opacity:** about 85% of the theme's own card colour instead of a blur (mock-ups at 78/86/92%: the photo
  still shows between and around the cards, and Light gets more readable than with the blur). Night keeps its
  own near-solid glass.
- **Order:** Lite ships first, on its own. New seasons (Winter, Christmas, Valentine's, St Patrick's, Spring,
  Summer, July 4th, the other major US holidays) come after, planned fully when we get to them; they will
  inherit Lite through the guard below.

## Behaviour

`<html data-lite="on|off">`, stamped by `theme.js` before paint like every other preference.

1. **Storage and precedence:** this device's choice in `localStorage` `fh.lite` (`on`/`off`); the default is
   `off`. `?lite=1` / `?lite=0` in the page URL writes it (so the kiosk URL can latch it). A bad stored value
   falls back to `off`. There is no house default: it is a property of a screen.
2. **API:** `setLite(v)` (validates `on`/`off`, writes, stamps live), exposed like `setSeason`.
3. **Settings:** the Seasonal looks card gets a "Lite" row: Off/On buttons with a one-line note ("For a
   slower screen such as a Raspberry Pi 3: keeps the photo, drops the blur and the moving leaves, bats and
   spiders"). It reflects the current value like the Season switch. The gear popover is not changed.
4. **Glass:** with `data-lite="on"` and a look painting, the wall's glass (cards, expand buttons, section
   titles, top bar) is `--glass` = 86% of the theme's `--surface`, `--glass-edge` unchanged, and
   `backdrop-filter: none`. The theme still owns the glass colour family (it is derived from `--surface`);
   the Lite rule is one selector set, not a per-theme copy. Night keeps `--glass` at 94% (it already has no
   blur) and wins over Lite.
5. **Motion:** with Lite on, these never display: the near layer (`body > .season-fx`, which holds the near
   leaves and the Halloween creatures), the far leaves (`.season .sn-leaves`), the far bats
   (`.season .sn-bat`). The photo layer's 1.2 s arrival fade is off. The JS walkers (spiders) already stand
   down when their layer is not showing; Lite must make them do so, and run no timer/animation work once
   they have.
6. **Settings preview tiles** (`.look-swatch`) are unchanged: they are previews of the look, drawn small and
   still.
7. **No look painting** (seasons off, or no season in the calendar today): Lite has no visible effect.
8. **Guard for future seasons:** a test fails if CSS animates a `.sn-*` class (or a rule under
   `body > .season` / `body > .season-fx`) that Lite's hide list does not cover, unless it is on a short
   allow-list of things that never move (the webs). A new season that puts motion in a new class must
   either use the covered layers or add itself to the Lite list.

## Out of scope

Automatic slow-screen detection, a house default, downscaling the photo for Lite (the photo stays full
sharpness: static once the blur is gone), changing weather or laundry animations, new seasons.

## Measuring on the Pi 3

Not measurable off the Pi. Before/after readings (operator, over SSH, a minute in each state): `top -b -n 2
-d 15 -o %CPU | head -15`, `vcgencmd get_throttled`, `vcgencmd measure_temp`, plus the GPU settings in
`/boot/firmware/config.txt` and `chromium --version`. Baselines wanted: season off, season on (full), season
on with Lite.

## Testing

`theme.js` tests: default off, stored value wins, invalid value falls back, `?lite=1`/`?lite=0` latch and
clear, `setLite` validates and re-stamps, no storage still works. Static guards: the Lite CSS block (glass
fill from `--surface`, `backdrop-filter: none` on every glass target, the three motion layers hidden, the
arrival fade off, `.look-swatch` untouched, night still wins, phone unaffected beyond the same rules) and the
future-season guard above. DOM tests: the Settings row renders and reflects the value; a spider's
`showing()` is false under Lite. Browser checks on the demo: every theme x a fall and a Halloween look with
Lite on and off, night, the phone, the Settings tiles; compare seasons-off pixel for pixel with main.
