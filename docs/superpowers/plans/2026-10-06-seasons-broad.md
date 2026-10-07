# New Seasons, PR 2: Winter, Spring and Summer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three broad seasons with three operator-picked looks each (nine photos), so the wall follows the whole year: Winter (Dec 1 to Feb 29), Spring (Mar 1 to May 31), Summer (Jun 1 to Aug 31).

**Architecture:** Pure registry-and-art work on the groundwork from PR 1 (`docs/superpowers/plans/2026-10-06-seasons-groundwork.md`): nine photos prepared with `scripts/prep-season-photo.py`, nine `SEASONS` entries (each season names its `drift` kind), a CSS token block per look (photo, focal point, accent, light-theme accent), three season marks, credits. The picker, windows, drift layer, Lite and the guards already exist.

**Tech Stack:** `theme.js` registry, `styles.css` tokens, Pillow (dev-only photo prep), node:test and pytest guards, headless-Edge visual checks.

**Spec:** `docs/superpowers/specs/2026-10-06-new-seasons-design.md`. **Standard:** `docs/seasonal-looks.md` (every look is held to it).

**Branching:** this PR is stacked on `feat/seasons-groundwork` (PR #19). Branch `feat/seasons-broad` from it; when PR #19 merges, rebase onto `main` (`git rebase --onto main feat/seasons-groundwork`) before opening this PR.

## The operator's picks (2026-10-06, from the contact sheets)

| Look id | Name | Photo (source) | Creator | Licence on Commons | Size |
|---|---|---|---|---|---|
| `winter-mthood` | Snowy Firs | `File:Snow Covered Trees, Mt Hood National Forest (36795929710).jpg` | U.S. Forest Service, Pacific Northwest Region | Public domain (`PD-USGov-USDA-FS`) | 5416x3696 |
| `winter-alpenglow` | Alpenglow | `File:Alpenglow on Snowy Star Dune and Crestone Peaks (31601451293).jpg` | Great Sand Dunes National Park and Preserve (NPS) | Public domain (`PD-USGov-NPS`) | 4608x3456 |
| `winter-cabin` | Winter Cabin | `File:A cabin among the snowy forest (Unsplash).jpg` | Gérôme Bruneau | CC0 (`{{Unsplash}}`, a pre-June-2017 Unsplash upload; see Task 1) | 3888x2592 |
| `spring-redbud` | Redbud Bloom | `File:Redbuds, Chatham University, 2023-04-20, 01.jpg` | Cbaile19 | CC0 | 3996x2664 |
| `spring-bluebonnets` | Bluebonnet Hills | `File:Bluebonnet field near Marble Falls in the Hill Country of Texas LCCN2014633112.tif` | Carol M. Highsmith (Library of Congress) | Public domain (`PD-Highsmith`) | 7360x4912 (TIFF) |
| `spring-france` | Spring in France | Art Institute of Chicago artwork 97292, "Spring in France" (1890, oil on canvas) | Robert William Vonnoh | Public domain (AIC open access) | 3000x2069 |
| `summer-sunflowers` | Sunflower Fields | `File:Sunflower Fields.jpg` | Wenchieh Yang | CC0 | 3264x2448 |
| `summer-lone-ranch` | Lone Ranch Sunset | `File:Sunset, Lone Ranch Beach, Oregon.jpg` | Bonnie Moreland | CC0 | 5184x3456 |
| `summer-wildflowers` | Coastal Wildflowers | `File:Summer wildflowers at Yaquina Head (48302262812).jpg` | BLM Oregon & Washington | Public domain (`PD-USGov-BLM`) | 4032x2268 |

The first look listed for each season is its `default: true` look. Winter paints `drift: "snow"`, Spring `drift: "petal"`, Summer `drift: "firefly"` (spec).

## Global Constraints

- Every look: a real photograph or public-domain artwork at **2560px wide, never softened**, through `scripts/prep-season-photo.py` (WebP, sRGB, metadata stripped); a file over 2.6 MB is re-encoded with `--quality 76`, never downsized (a test enforces the cap).
- Season ids are bare lowercase words (`winter`, `spring`, `summer`); look ids are `<season>-<name>` (hyphens only after the season). Registry order is `winter`, `spring`, `summer`, `halloween`, `fall` (the first window that matches wins; none of these overlap Halloween/Fall).
- A look sets only its photo, focal point, accent (+ ink + soft), a lighter-theme accent, and optionally its drift bit colours. It never sets a theme-owned token (a test fails if it does).
- The accent comes from the photo: a lighter tone for the dark themes and a deeper one for Light and Soft so it reads on white glass (check contrast on the glass by eye and by number, at least 4.5:1 for the accent against the Light glass).
- Judge every look behind the glass at full size (every look x all five themes, seasons off, night, reduced motion, Lite on, the phone, the gear popover, the Settings tiles); a thumbnail is not a review.
- Photos stay in the repo only as the prepared 2560px WebP; originals live outside the repo. Every file in `static/seasons/` gets a `CREDITS.md` row (a test enforces it). The repo is public and MIT: nothing may enter it that is not public domain or CC0 (or the permissive licences the file already lists).
- Each src commit adds its own NEW "- " bullet under CHANGELOG `## [Unreleased]` (hook). No real IPs or tokens.
- Run Python with the scratchpad venv, `TZ=UTC`, `PYTHONUTF8=1`; 49 Python tests fail identically on clean main on Windows (backup 30, install_hooks 13, caldav 2, google_client 2, check_changelog 1, api health 1). Write multi-line edit scripts to a file with the Write tool (the shell halves backslashes).

## Review Focus

- **Licences:** the cabin photo is a Commons mirror of an Unsplash upload (taken 2016-02-17, uploaded to Commons 2017-08-23). The standard allows only Unsplash photos uploaded before June 2017. Confirm on the Unsplash/Commons source page (Task 1) and record what was verified.
- **Contrast over bright photos:** snow, a white-sky sunflower field and a pale painting are the risk. The empty check rings, struck-through calendar lines, the faint section titles and small mono text must stay readable in Light and Soft (the standard lists these as the first things to vanish).
- **Crop:** the wall shows the whole 16:9 frame, the phone shows roughly the middle third; the 4:3 sunflower photo and the 3:2 ones are cropped by `cover`. Each look's `--sn-pos` must keep its subject in both.
- **Calendar behaviour:** on any day in Dec to Feb the wall paints Winter, Mar to May Spring, Jun to Aug Summer; Sep to Nov Fall and Oct Halloween as before; nothing paints on a wall with seasons off; the picker lists Winter, Spring and Summer under "Coming up" in October.
- **Drift:** snow reads as snow (not dust) on the dark-blue firs and on white snow; fireflies on a daytime sunflower photo are nearly invisible (note it; they suit the dusk beach look) but must not look like dirt on the photo.
- **Storage choices:** `fh.look.winter` etc. are the keys; a device that never picked gets the season's default.
- **Size budget:** the nine WebPs together (record the total in the PR).

---

### Task 1: Fetch and prepare the nine photos; credit them

**Files:**
- Create: `src/family_hub/web/static/seasons/{winter-mthood,winter-alpenglow,winter-cabin,spring-redbud,spring-bluebonnets,spring-france,summer-sunflowers,summer-lone-ranch,summer-wildflowers}.webp`
- Modify: `src/family_hub/web/static/seasons/CREDITS.md`

**Interfaces:**
- Consumes: `scripts/season-photo-search.py fetch`, `scripts/prep-season-photo.py` (needs `pip install pillow` in the scratchpad venv; dev-only).
- Produces: the nine prepared photos and their credit rows.

- [ ] **Step 1: Fetch the originals into a folder OUTSIDE the repo**

The candidate lists are in `C:\Users\mrtim\Documents\family-hub-season-photos\{winter,spring,summer}\candidates.json` (already written by the contact-sheet step; each look's `SOURCE:ID` is on its sheet). For each pick run, for example:

```
python scripts/season-photo-search.py fetch "commons:File:Snow Covered Trees, Mt Hood National Forest (36795929710).jpg" --out C:\Users\mrtim\Documents\family-hub-season-photos\winter\winter-mthood.jpg
python scripts/season-photo-search.py fetch aic:97292 --out C:\Users\mrtim\Documents\family-hub-season-photos\spring\spring-france.jpg
```

The Highsmith bluebonnet original is a very large TIFF; fetch it as is (one-time, dev only) and let Pillow read it. Each `fetch` prints a draft `CREDITS.md` row. Expected: nine files saved, nine rows printed, no `.part` files left.

- [ ] **Step 2: Verify the cabin photo's licence history**

Open the Commons page (`https://commons.wikimedia.org/wiki/File:A_cabin_among_the_snowy_forest_(Unsplash).jpg`) and its Unsplash source link. The photo is CC0 on Commons via the `{{Unsplash}}` template, which Commons applies only to uploads made before Unsplash's June 2017 licence change. Record in the ledger what the page says (the Unsplash upload date or the template wording). If it cannot be shown to predate June 2017, STOP and ask the operator to pick a replacement winter look (do not ship it).

- [ ] **Step 3: Prepare each photo**

```
python scripts/prep-season-photo.py <original> <look-id>
```
for each of the nine look ids in the table. Expected: nine files in `static/seasons/`, each 2560px wide (the AIC painting is 3000px source, so also 2560) and at most 2.6 MB; for any over the cap rerun with `--quality 76`. Record the nine sizes and their total.

- [ ] **Step 4: Credit them**

Under `## Photos` in `CREDITS.md` add one row per file in the existing column format (file, "title", creator, source link, licence), using the table above and the rows `fetch` printed (fix up creator names to plain text). For the cabin photo include the Unsplash verification from Step 2. Run `<venv>/python -m pytest tests/test_static.py -q -k credit` and expect `test_season_art_files_exist_and_are_credited` to pass.

- [ ] **Step 5: Commit**

No JS or CSS changed, so the changelog hook does not apply to this commit unless it touches `src/`; the WebPs and CREDITS are under `src/`, so add a CHANGELOG `### Added` bullet: `- Seasons: the artwork for Winter, Spring and Summer (nine photos and paintings, all public domain or CC0, credited); nothing paints them yet.`

```bash
git add src/family_hub/web/static/seasons CHANGELOG.md
git commit -m "feat: artwork for the Winter, Spring and Summer looks (nothing paints it yet)"
```

---

### Task 2: Marks, registry entries and look tokens

**Files:**
- Create: `src/family_hub/web/static/seasons/mark-snowflake.svg`, `mark-blossom.svg`, `mark-sun.svg` (+ `CREDITS.md` rows: "Self-made abstract, CC0")
- Modify: `src/family_hub/web/static/theme.js` (`SEASONS`), `src/family_hub/web/static/styles.css`, `CHANGELOG.md`

**Interfaces:**
- Consumes: the registry fields from PR 1 (`from`/`to`, `drift`, `looks[]`), the existing guards (`test_every_look_sets_its_photo_and_accent_and_leaves_the_theme_alone`, `test_every_look_ships_a_light_clean_photo_and_a_mark`, `test_season_art_files_exist_and_are_credited`, `test_no_look_rule_anywhere_sets_a_theme_owned_token`, `theme.test.mjs` "the season registry is well formed").
- Produces: the nine looks painting from the registry.

- [ ] **Step 1: The registry entries (RED first)**

Add to `SEASONS` in `theme.js`, before `halloween` (order: `winter`, `spring`, `summer`, `halloween`, `fall`):

```javascript
    { id: "winter", name: "Winter", from: [12, 1], to: [2, 29], drift: "snow", looks: [
      { id: "winter-mthood", name: "Snowy Firs", blurb: "Snow-laden firs under a deep blue sky", credit: "Photo by the U.S. Forest Service", default: true },
      { id: "winter-alpenglow", name: "Alpenglow", blurb: "Pink evening light on snowy dunes and peaks", credit: "Photo by the National Park Service" },
      { id: "winter-cabin", name: "Winter Cabin", blurb: "A cabin among the snowy forest", credit: "Photo by Gérôme Bruneau" },
    ] },
    { id: "spring", name: "Spring", from: [3, 1], to: [5, 31], drift: "petal", looks: [
      { id: "spring-redbud", name: "Redbud Bloom", blurb: "Redbud branches in full bloom", credit: "Photo by Cbaile19", default: true },
      { id: "spring-bluebonnets", name: "Bluebonnet Hills", blurb: "A bluebonnet field in the Texas Hill Country", credit: "Photo by Carol M. Highsmith" },
      { id: "spring-france", name: "Spring in France", blurb: "A painted spring meadow, 1890", credit: "Painting by Robert William Vonnoh" },
    ] },
    { id: "summer", name: "Summer", from: [6, 1], to: [8, 31], drift: "firefly", looks: [
      { id: "summer-sunflowers", name: "Sunflower Fields", blurb: "Sunflowers under a summer sky", credit: "Photo by Wenchieh Yang", default: true },
      { id: "summer-lone-ranch", name: "Lone Ranch Sunset", blurb: "The sun going down over an Oregon beach", credit: "Photo by Bonnie Moreland" },
      { id: "summer-wildflowers", name: "Coastal Wildflowers", blurb: "Foxgloves above the Oregon coast", credit: "Photo by the Bureau of Land Management" },
    ] },
```

(write the `é` of Gérôme as is: the file is UTF-8). Run `TZ=UTC node --test tests/js/*.test.mjs` and `<venv>/python -m pytest tests/test_static.py -q`. Expected RED: the look-token, mark and photo-guard tests fail for every new look (no token block, no mark); the registry test passes; the Settings picker tests that count the real registry's seasons may need their expectations updated (rule on the smallest change that keeps their meaning and ledger it).

- [ ] **Step 2: Look at each photo and choose its focal point**

For each look, open the prepared WebP and the contact-sheet crop and set `--sn-pos` so the subject survives both the 16:9 wall crop and the phone's middle third (for example `center 35%` keeps the sky and the treetops of the firs; the sunflower photo is 4:3, so choose which band of it shows). Mock each behind the wall (headless Edge against the demo, `html[data-look] { --sn-scene: url(...) !important; --sn-pos: ... !important }`, as in the contact-sheet trials) in Grey and Light at 1920x1080 and 390x844 and READ the images. Record the chosen `--sn-pos` for each in the ledger.

- [ ] **Step 3: Choose each look's accent from its photo**

Sample the photo's colours (Pillow `quantize`, a scratch script outside the repo) and pick, per look, a vivid mid-tone that belongs to the photo (the snow's blue shadow, the alpenglow rose, the cabin's red, the redbud magenta, the bluebonnet blue, the painting's meadow green, the sunflower yellow, the sunset orange, the foxglove purple). Pair each with: `--accent-ink` (dark ink for light accents, white for deep ones), `--accent-soft` (the accent at 13 to 18% alpha), and a DEEPER light-theme accent that reaches 4.5:1 against the Light glass (compute the ratio; do not eyeball it).

- [ ] **Step 4: The token blocks**

For each look add, next to the existing look blocks in `styles.css` (copy the shape of `fall-aspen-grove`):

```css
/* ---- Snowy Firs: snow-laden firs under a deep blue sky (U.S. Forest Service, public domain) ---- */
:root[data-look="winter-mthood"][data-theme][data-accent],
.look-swatch[data-look="winter-mthood"] {
  --accent:#...; --accent-ink:#...; --accent-soft:rgba(...);
  --sn-scene:url("seasons/winter-mthood.webp"); --sn-pos:center 35%;
}
:root[data-look="winter-mthood"][data-accent]:is([data-theme="light"],[data-theme="soft"]),
:root:is([data-theme="light"],[data-theme="soft"]) .look-swatch[data-look="winter-mthood"] {
  --accent:#...; --accent-ink:#FFFFFF; --accent-soft:rgba(...);
}
```
(nine times, with the chosen values). Optionally a per-season drift colour block, for example `:root[data-look^="spring-"], .look-swatch[data-look^="spring-"] { --sn-bit-1:#...; --sn-bit-2:#...; }` to tint the petals to the photo (leave snow white; leave fireflies warm).

- [ ] **Step 5: The marks**

Create three one-colour SVGs (viewBox `0 0 100 100`, single fill, no scene): `mark-snowflake.svg` (six arms with short barbs, drawn with strokes), `mark-blossom.svg` (five round petals around a small centre), `mark-sun.svg` (a disc with eight short rays). Add `CREDITS.md` rows ("Self-made abstract, CC0") and the mark rules next to the existing ones, one per season prefix:

```css
[data-look^="winter-"] .season-mark,
.look-swatch[data-look^="winter-"] .look-mark { --mark: url("seasons/mark-snowflake.svg"); }
[data-look^="spring-"] .season-mark,
.look-swatch[data-look^="spring-"] .look-mark { --mark: url("seasons/mark-blossom.svg"); }
[data-look^="summer-"] .season-mark,
.look-swatch[data-look^="summer-"] .look-mark { --mark: url("seasons/mark-sun.svg"); }
```

- [ ] **Step 6: Run to verify GREEN**

Run `TZ=UTC node --test tests/js/*.test.mjs` and `<venv>/python -m pytest tests/test_static.py tests/test_no_house_data.py -q`. Expected: all pass, including the per-look guards for all nine, the credit guard, and the no-theme-token guard.

- [ ] **Step 7: Mutation-check**

(a) drop one look's token block, (b) drop a mark rule, (c) remove a look's `--sn-scene`, (d) misspell a photo file name in CSS, (e) set a theme-owned token (`--ink`) in one look block, (f) delete a `CREDITS.md` row. Each must fail a guard; restore and `cmp`.

- [ ] **Step 8: Commit**

CHANGELOG `### Added`: `- Seasons: Winter (Dec 1 to Feb 29), Spring (Mar 1 to May 31) and Summer (Jun 1 to Aug 31) with three looks each, each with its own accent and a season mark; snow, petals and fireflies drift over them. Turn Seasonal looks on in Settings and pick the photos you like.`

```bash
git add src/family_hub/web/static tests CHANGELOG.md
git commit -m "feat: Winter, Spring and Summer seasons with three looks each"
```

---

### Task 3: Calendar behaviour and picker tests

**Files:**
- Modify: `tests/js/seasons.test.mjs` (add a real-registry test), `tests/js/hub-dom.test.mjs` only if existing picker tests assumed two seasons.

- [ ] **Step 1: Write the failing test.** In `seasons.test.mjs` add a test that loads the REAL registry (no fixtures) and asserts, via `T.seasonFor(date)` (default list): every date from Sep 1 to Aug 31 of 2026/27 resolves to the expected season id (`winter` for Dec 1 to Feb 29 (2028 leap), `spring` Mar 1 to May 31, `summer` Jun 1 to Aug 31, `halloween` Oct 1 to 31, `fall` Sep 1 to 30 and Nov 1 to 30), that Halloween/Fall still win in their windows, and that `T.seasonOutlook(oct6)` puts `halloween`+`fall` in `active`, `winter`/`spring`/`summer` in `upcoming` in that order, and `rest` empty. Also assert each season's default look is `<season>-<first name>` and that every look id is unique across seasons.
- [ ] **Step 2: Run to verify** it passes (the registry already has the data; if it fails, the registry or the order is wrong: fix the code, not the test). Mutation-check by swapping `winter` and `fall` order and by moving Spring's `to` to `[5, 30]`.
- [ ] **Step 3: Commit** (CHANGELOG `### Added`: `- Seasons: tests pin which season paints on every day of the year with Winter, Spring and Summer in the registry.`).

---

### Task 4: The visual gates

**Files:** none committed unless a fix is needed (each fix gets a test first).

- [ ] **Step 1: The matrix.** On the demo (`DEMO=1`, port 8199) force each look (`setSeason('on'); document.documentElement.setAttribute('data-look', '<id>')` re-asserted on an interval, as the clock tick re-derives it, plus the matching `data-drift`) and capture 1920x1080 for every look x Light, Soft, Blue, Grey, Black (45 shots). READ every image. For each, check against the standard: the photo reads as the season, the text over it is readable, the empty check rings and struck-through lines are visible, the accent is legible on the glass, the drift (snow, petals, fireflies) is visible but quiet and never covers words for long.
- [ ] **Step 2: The rest of the checklist,** for at least one look per season and the worst-contrast look (the snow photos, the sunflower sky, the pale painting): night mode (`is-night`), reduced motion (CDP `Emulation.setEmulatedMedia`), Lite on (no blur, no drift), the phone at 390 and 360 (no sideways spill, the gear popover above the cards, a two-digit hour on the clock), the Settings page (picker grouping, all nine tiles render their photo, resting drift and mark), and seasons off (a wall with `data-season="off"` is unchanged from main outside the animated panels and the clock).
- [ ] **Step 3: Fix what fails.** Each real problem gets a failing test first where it can be tested (a token, a selector, a contrast ratio), or a documented eyeball fix (a `--sn-pos`, an accent) recorded in the ledger. Typical fixes: nudge a focal point, deepen a light-theme accent, raise a tile's contrast.
- [ ] **Step 4: Commit any fixes** (one commit per concern, each with its CHANGELOG bullet).

---

### Task 5: Docs, the showcase image, full verification, review, PR

- [ ] **Step 1: Docs.** README: the Seasonal looks bullet names Winter, Spring and Summer with their dates and says the picker lists the seasons by what is coming up; `docs/seasonal-looks.md`: the "Shipped so far" paragraph (now fall, Halloween, winter, spring, summer) and the next-in-order line (the holidays). Refresh `docs/seasons.jpg` (the README's showcase of the looks) so it includes the new looks: capture the walls from the demo (forced looks) and compose the same layout the existing image uses; keep it under the size the repo already allows.
- [ ] **Step 2: Full suites.** `TZ=UTC node --test tests/js/*.test.mjs`; the full pytest (only the 49 known Windows failures); `test_no_house_data` (it reads tracked files only, so run it after committing); record the nine WebP sizes and their total.
- [ ] **Step 3: Review.** A fresh-context review of the whole branch with this plan's Review Focus verbatim; apply Critical/Important in ONE fix pass (each fix RED then GREEN); ledger minors.
- [ ] **Step 4: Push and PR** with `gh pr create -R dapperdodger/family-hub --base main --head feat/seasons-broad` (plain `gh pr create` resolves to the wrong owner); if PR #19 has not merged, say so in the body and base on `feat/seasons-groundwork` instead. The body ends with the attribution line from the session reminder.
- [ ] **Step 5: Hand-off for PR 3 (holidays).** Run the photo search helper for the first holiday group with the operator (Thanksgiving and Christmas first, then the rest by date) before writing its plan.
