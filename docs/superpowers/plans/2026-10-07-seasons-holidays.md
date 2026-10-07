# New Seasons, PR 3: The Holidays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ten holiday seasons on top of the whole-year calendar from PR 2, with 29 operator-picked looks: Thanksgiving (4), Christmas (3), New Year's (3), MLK Day (1), Valentine's Day (3), St Patrick's Day (3), Easter (3), Mother's Day (3), Father's Day (3) and Fourth of July (3).

**Architecture:** Pure registry-and-art work on the machinery PRs 1 and 2 built: 29 photos prepared with `scripts/prep-season-photo.py`, ten `SEASONS` entries (fixed or moving windows, listed before the broad season each one sits in), a CSS token block per look, five new season marks, credits. The one new behaviour is Thanksgiving painting the fall leaves (the leaf layer is keyed on `fall-` today). The picker, drift layers, Lite and the guards already exist.

**Tech Stack:** `theme.js` registry, `styles.css` tokens, Pillow (dev-only photo prep), node:test and pytest guards, headless-Edge visual checks.

**Spec:** `docs/superpowers/specs/2026-10-06-new-seasons-design.md` (the holiday table, windows and motion are its binding text). **Standard:** `docs/seasonal-looks.md`.

**Branching:** branch `feat/seasons-holidays` from `main` (PR #20 is merged, so this is not stacked). Open the PR with `gh pr create -R dapperdodger/family-hub --base main --head feat/seasons-holidays` (plain `gh pr create` resolves to the wrong owner).

## Working environment (the old scratchpad is gone)

- Scratch files live OUTSIDE the repo in `C:\Users\mrtim\Documents\family-hub-season-photos\_work\` (below: `$W`). Originals and candidate lists live in `C:\Users\mrtim\Documents\family-hub-season-photos\<season>\`. Nothing in these folders is ever committed.
- The system Python's pytest is broken (a trio/anyio plugin error), so Task 1 builds a venv at `$W\venv` the way CI does. Every command below uses `PY=$W/venv/Scripts/python`, `PYTHONPATH=src`, `TZ=UTC`, `PYTHONUTF8=1`.
- `$W` already holds `shot.mjs` (the headless-Edge CDP screenshot driver: `node shot.mjs scenarios.json`, scenarios are `{out,w,h,mobile,url,js,wait,settle,evalOut,full}`), `sheet.py`, `sheet2.py` and the harvest JSON for every holiday (`$W\harvest\hol-<season>.json`, `hol-mlkpeople.json`, `hol-clover.json`). Each harvest entry has `source`, `id`, `title`, `creator`, `licence`, `page`, `original`, `width`, `height`.
- The demo wall for screenshots: from the repo root, `DEMO=1 DB_PATH="$W/demo.db" CONFIG_PATH=config.demo.json PYTHONPATH=src DISABLE_SYNC=1 $PY -m uvicorn family_hub.app:app --port 8199` (run in the background; a server from an earlier session may already answer on 8199 and it serves the checked-out tree).
- Write multi-line edit scripts to a file with the Write tool (the shell halves backslashes) and read/write repo files with `newline=''` (the working copy may be CRLF; `CREDITS.md` must stay LF, a test enforces it). A shared helper makes that routine; create it once (Task 1, Step 1): `$W\edit.py`.

## The operator's picks (2026-10-07, from the contact sheets)

All 29 are public domain or CC0 on Wikimedia Commons; 20 of them are pre-June-2017 Unsplash mirrors that Task 1 must verify one by one. The `ref` is what the fetch helper takes; the look id is the prepared file name (`static/seasons/<look id>.webp`).

| Season | Look id | Name | Commons file |
|---|---|---|---|
| thanksgiving | `thanksgiving-pumpkins` | Heirloom Pumpkins | `File:Cucurbita 2011 G1.jpg` |
| thanksgiving | `thanksgiving-cranberries` | Cranberry Harvest | `File:Cranberrys beim Ernten.jpeg` |
| thanksgiving | `thanksgiving-pumpkin-bowl` | Pumpkin Bowl | `File:2016 USDA Farmers Market (20161021-AMS-LSC-0081).jpg` |
| thanksgiving | `thanksgiving-turkey` | Wild Turkey | `File:Wild Turkey (41629927372).jpg` |
| christmas | `christmas-santa` | Santa Lights | `File:A figure of Christmas (Unsplash).jpg` |
| christmas | `christmas-village` | Gingerbread Village | `File:Christmas holiday model (Unsplash).jpg` |
| christmas | `christmas-snowmen` | Snowmen | `File:Snowmen at Christmas (Unsplash).jpg` |
| newyears | `newyears-sparkler` | Sparkler | `File:Mumbai sparkler (Unsplash).jpg` |
| newyears | `newyears-fireworks` | Fireworks over Water | `File:Fireworks over water (Unsplash).jpg` |
| newyears | `newyears-champagne` | Champagne | `File:Champagne-glasses-1940262 1920.jpg` (Pixabay, 2016) |
| mlkday | `mlkday-march` | March on Washington | `File:Martin Luther King Jr National Historic Site (36233249121).jpg` |
| valentines | `valentines-bouquet` | Pink Bouquet | `File:Pink rose bouquet (Unsplash).jpg` |
| valentines | `valentines-tulips` | Red Tulips | `File:Luxurious red tulips (Unsplash).jpg` |
| valentines | `valentines-rose` | Red Rose | `File:Red rose in macro (Unsplash).jpg` |
| stpatricks | `stpatricks-countryside` | Green Countryside | `File:Green countryside (Unsplash).jpg` |
| stpatricks | `stpatricks-bay` | Coastal Bay | `File:Coastal bay cliffs (Unsplash).jpg` |
| stpatricks | `stpatricks-clover` | Four-Leaf Clover | `File:Four-leaf Clover Trifolium repens 1.jpg` |
| easter | `easter-eggs` | Easter Eggs | `File:Easter candy (Unsplash).jpg` |
| easter | `easter-ducklings` | Ducklings | `File:Duckling chicks (Unsplash).jpg` |
| easter | `easter-rabbit` | Brown Rabbit | `File:Brown rabbit green grass (Unsplash).jpg` |
| mothersday | `mothersday-tulips` | Tulip Bouquet | `File:Tulip-bouquet-vienna (Unsplash).jpg` |
| mothersday | `mothersday-blossom` | Spring Blossom | `File:Blossom-austria-spring (Unsplash).jpg` |
| mothersday | `mothersday-wildflowers` | Wildflower Bouquet | `File:Bouquet of wildflowers, Ehrenbach.jpg` |
| fathersday | `fathersday-fjord` | Fjord Sunset | `File:Nordfjordeid river sunset (Unsplash).jpg` |
| fathersday | `fathersday-jeep` | Road Trip | `File:Retro jeep with canoe on roof (Unsplash).jpg` |
| fathersday | `fathersday-campfire` | Campfire Cooking | `File:Campfire Cooking (Unsplash).jpg` |
| julyfourth | `julyfourth-fireworks` | National Mall Fireworks | `File:Independence Day Fireworks in the National Mall.jpg` |
| julyfourth | `julyfourth-sparkler` | Flag and Sparkler | `File:American Flag and Sparkler (Unsplash).jpg` |
| julyfourth | `julyfourth-flag` | Flag on a Pole | `File:American Flag On A Pole (Unsplash).jpg` |

The first look listed for each season is its `default: true` look. **Operator rulings on the picks:** keep `julyfourth-fireworks` although its Commons page names no author (NPS photo gallery, `PD-USGov-NPS`, plus a stray `cc-by-sa-2.0` tag): the credit row says exactly that. `mlkday` has one look. Thanksgiving has four (the spec says three; the operator picked four).

## The calendar (spec, binding)

Registry order is the rule (the first window that holds today wins): `newyears, christmas, mlkday, valentines, winter, stpatricks, easter, mothersday, spring, fathersday, julyfourth, summer, halloween, thanksgiving, fall`. Windows: New Year's Dec 27 to Jan 2 (wraps); Christmas Dec 1 to Dec 26; MLK Day the Friday to the Monday of the third Monday of January (`WINDOWS.mlkDay`); Valentine's Feb 1 to Feb 14; St Patrick's Mar 1 to Mar 17; Easter the 14 days before Easter Sunday through Easter Monday (`WINDOWS.easter`); Mother's Day the Monday to the Sunday of the second Sunday of May (`WINDOWS.mothersDay`); Father's Day the Thursday to the Sunday of the third Sunday of June (`WINDOWS.fathersDay`); Fourth of July Jun 25 to Jul 4; Thanksgiving the Monday ten days before the fourth Thursday of November through the Sunday after it (`WINDOWS.thanksgiving`). Motion: Christmas snow; New Year's and Fourth of July sparkle; Valentine's, Easter and Mother's Day petals; St Patrick's clover; Thanksgiving the fall leaves; MLK Day and Father's Day none. Intentional overlaps (all tested): St Patrick's wins Mar 9 to 17 over an early Easter; Christmas wins Dec 1 over a late Thanksgiving week (2030); every holiday beats the broad season it sits in.

## Global Constraints

- Every look: a real photograph at **2560px wide, never softened**, through `scripts/prep-season-photo.py` (WebP, sRGB, metadata stripped); over 2.6 MB means `--quality 76`, never a smaller size (a test enforces the cap). The 29 files together are about 20 to 30 MB; record the total for the PR body.
- Season ids are bare lowercase words; look ids are `<seasonid>-<name>` (extra hyphens only after the season id, e.g. `thanksgiving-pumpkin-bowl`).
- A look sets only its photo, focal point, accent (+ ink + soft), a deeper light-theme accent, and for Thanksgiving its four leaf colours. It never sets a theme-owned token (a test fails if it does). The light-theme accent must reach 4.5:1 against both `#FFFFFF` and the Soft surface `#F7F3EB` (computed, not eyeballed).
- Licences: public domain, CC0, or (never needed here) the permissive ones `CREDITS.md` already lists. Never share-alike, never non-commercial. Unsplash photos only if they were on Unsplash before June 2017 (Task 1 proves it per file). Every file in `static/seasons/` gets a `CREDITS.md` row (a test enforces it); the repo is public and MIT.
- Judge every look behind the glass at full size (Task 6). A thumbnail is not a review.
- Each `src/` commit adds its own NEW "- " bullet under CHANGELOG `## [Unreleased]` (the hook enforces it; a bullet goes under the existing `### Added` heading). No real IPs or tokens anywhere.
- Python: the baseline of known failures on this Windows machine is measured in Task 1 (CI-style venv); do not assume the old "49".

## Review Focus

1. **Licence evidence per file.** 20 Unsplash mirrors (each needs a pre-June-2017 proof), the Pixabay champagne photo (CC0 only if it predates Pixabay's January 2019 licence change), `julyfourth-fireworks` (author unknown, stray CC-BY-SA tag, operator accepted), the NPS MLK photo (PD as a 1963 photograph published without notice), and the USDA / USFWS federal photos. Check every `CREDITS.md` row against the live Commons page.
2. **Calendar overlaps and wraps.** New Year's wrap and Feb 29; St Patrick's vs an early Easter (2008, Mar 9 to 17); Christmas vs a late Thanksgiving (2030, Dec 1); Valentine's and MLK Day inside Winter; Thanksgiving inside Fall; Mother's/Father's weeks inside Spring/Summer. The committed calendar fixture comes from an independent Python oracle; check it does not just mirror the JS.
3. **Contrast over bright or dense photos.** Foil Easter eggs, the champagne close-up on black, the yellow pumpkin bowl, the tulip masses, the black-and-white March crowd, snow and fireworks. Empty check rings, struck-through calendar lines, faint section titles and small mono text must stay readable in Light and Soft; the light accents reach 4.5:1 on opaque white/Soft but the real glass is translucent, so also read the full-size shots.
4. **Motion per season.** Thanksgiving must show the leaves (new selector) and Lite must hide them; clover drift must be visible but not busy on `stpatricks-clover` (a clover photo); sparkle must read on the dark fireworks and the daytime flag; petals are tinted per season (shared blocks), not left pink; MLK Day and Father's Day show none.
5. **Storage and picker.** `fh.look.<season>` keys are per season, so a device that picked a Fall look still gets Thanksgiving's default in Thanksgiving week (expected, state it in the docs); the picker with 15 seasons (In season now / Coming up / More seasons) lists every holiday once, and moving seasons show their `when` text.
6. **Crops.** Each look's `--sn-pos` keeps its subject out from behind the card columns on the 16:9 wall and in the phone's middle third (the jeep sits low, the champagne coupes and the four-leaf clover are small).
7. **Size budget** of the 29 WebPs, and that no tracked file contains EXIF/XMP.

---

### Task 1: Environment, licence proof, photos and credits

**Files:**
- Create: `static/seasons/<look id>.webp` for the 29 looks (under `src/family_hub/web/static/seasons/`)
- Modify: `src/family_hub/web/static/seasons/CREDITS.md`, `CHANGELOG.md`
- Scratch only (`$W`, never committed): `edit.py`, `picks.py`, `make_candidates.py`, `fetch_all.py`, `verify_licences.py`, `credits_rows.py`, `licences.json`

**Interfaces:**
- Consumes: `scripts/season-photo-search.py fetch` (needs `candidates.json` next to `--out`), `scripts/prep-season-photo.py SOURCE look-id`.
- Produces: the 29 prepared photos named exactly as the look ids, 29 `CREDITS.md` rows, `$W\licences.json` (per look: verdict and the Unsplash date used by the credits rows).

- [ ] **Step 1: Build the venv, the edit helper and the baseline**

```
W=/c/Users/mrtim/Documents/family-hub-season-photos/_work
cd /c/Users/mrtim/Documents/family-hub
python -m venv $W/venv
$W/venv/Scripts/python -m pip install -q -r requirements.txt -c requirements.lock pytest httpx pillow
PYTHONPATH=src TZ=UTC PYTHONUTF8=1 $W/venv/Scripts/python -m pytest tests -q -p no:cacheprovider > $W/baseline.txt 2>&1; tail -3 $W/baseline.txt
TZ=UTC node --test tests/js/*.test.mjs 2>&1 | grep -E "^# (pass|fail)"
```
Expected: node `# fail 0`; pytest ends with a failure count (record it and the failing test names with `grep FAILED $W/baseline.txt | sed 's/ - .*//' | sort > $W/baseline-failures.txt` in the ledger; they are the Windows-only known failures, not yours).

Create `$W\edit.py` (Write tool):

```python
import os

def edit(path, fn):
    """Read a text file keeping its line endings, apply fn to LF text, write it back."""
    s = open(path, encoding="utf-8", newline="").read()
    crlf = "\r\n" in s
    out = fn(s.replace("\r\n", "\n"))
    open(path, "w", encoding="utf-8", newline="").write(out.replace("\n", "\r\n") if crlf else out)

def sub(s, old, new):
    assert s.count(old) == 1, f"expected exactly one: {old[:70]!r} (found {s.count(old)})"
    return s.replace(old, new)
```

- [ ] **Step 2: Write the picks table and the candidate lists**

Create `$W\picks.py` with the 29 rows of the picks table above:

```python
PHOTOS = r"C:\Users\mrtim\Documents\family-hub-season-photos"
# (season id, look id, Commons title)
PICKS = [
    ("thanksgiving", "thanksgiving-pumpkins", "File:Cucurbita 2011 G1.jpg"),
    ("thanksgiving", "thanksgiving-cranberries", "File:Cranberrys beim Ernten.jpeg"),
    ("thanksgiving", "thanksgiving-pumpkin-bowl", "File:2016 USDA Farmers Market (20161021-AMS-LSC-0081).jpg"),
    ("thanksgiving", "thanksgiving-turkey", "File:Wild Turkey (41629927372).jpg"),
    ("christmas", "christmas-santa", "File:A figure of Christmas (Unsplash).jpg"),
    ("christmas", "christmas-village", "File:Christmas holiday model (Unsplash).jpg"),
    ("christmas", "christmas-snowmen", "File:Snowmen at Christmas (Unsplash).jpg"),
    ("newyears", "newyears-sparkler", "File:Mumbai sparkler (Unsplash).jpg"),
    ("newyears", "newyears-fireworks", "File:Fireworks over water (Unsplash).jpg"),
    ("newyears", "newyears-champagne", "File:Champagne-glasses-1940262 1920.jpg"),
    ("mlkday", "mlkday-march", "File:Martin Luther King Jr National Historic Site (36233249121).jpg"),
    ("valentines", "valentines-bouquet", "File:Pink rose bouquet (Unsplash).jpg"),
    ("valentines", "valentines-tulips", "File:Luxurious red tulips (Unsplash).jpg"),
    ("valentines", "valentines-rose", "File:Red rose in macro (Unsplash).jpg"),
    ("stpatricks", "stpatricks-countryside", "File:Green countryside (Unsplash).jpg"),
    ("stpatricks", "stpatricks-bay", "File:Coastal bay cliffs (Unsplash).jpg"),
    ("stpatricks", "stpatricks-clover", "File:Four-leaf Clover Trifolium repens 1.jpg"),
    ("easter", "easter-eggs", "File:Easter candy (Unsplash).jpg"),
    ("easter", "easter-ducklings", "File:Duckling chicks (Unsplash).jpg"),
    ("easter", "easter-rabbit", "File:Brown rabbit green grass (Unsplash).jpg"),
    ("mothersday", "mothersday-tulips", "File:Tulip-bouquet-vienna (Unsplash).jpg"),
    ("mothersday", "mothersday-blossom", "File:Blossom-austria-spring (Unsplash).jpg"),
    ("mothersday", "mothersday-wildflowers", "File:Bouquet of wildflowers, Ehrenbach.jpg"),
    ("fathersday", "fathersday-fjord", "File:Nordfjordeid river sunset (Unsplash).jpg"),
    ("fathersday", "fathersday-jeep", "File:Retro jeep with canoe on roof (Unsplash).jpg"),
    ("fathersday", "fathersday-campfire", "File:Campfire Cooking (Unsplash).jpg"),
    ("julyfourth", "julyfourth-fireworks", "File:Independence Day Fireworks in the National Mall.jpg"),
    ("julyfourth", "julyfourth-sparkler", "File:American Flag and Sparkler (Unsplash).jpg"),
    ("julyfourth", "julyfourth-flag", "File:American Flag On A Pole (Unsplash).jpg"),
]
```

Create `$W\make_candidates.py`: it looks every pick up in all the harvest files and writes one `candidates.json` per season folder (the fetch helper requires it):

```python
import json, glob, os
from pathlib import Path
from picks import PICKS, PHOTOS

pool = {}
for f in glob.glob(str(Path(__file__).parent / "harvest" / "hol-*.json")):
    for c in json.load(open(f, encoding="utf-8")):
        pool[(c["source"], c["id"])] = c
missing = []
by_season = {}
for season, look, title in PICKS:
    c = pool.get(("commons", title))
    if not c:
        missing.append(title)
        continue
    by_season.setdefault(season, []).append(c)
for season, items in by_season.items():
    d = Path(PHOTOS) / season
    d.mkdir(parents=True, exist_ok=True)
    (d / "candidates.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
print("seasons:", len(by_season), "missing:", missing)
assert not missing, missing
```
Run: `cd $W && PYTHONUTF8=1 python make_candidates.py`. Expected: `seasons: 10 missing: []`.

- [ ] **Step 3: Fetch the 29 originals (background; Wikimedia rate-limits)**

Create `$W\fetch_all.py` (skips files already present, retries with growing waits):

```python
import subprocess, sys, time
from pathlib import Path
from picks import PICKS, PHOTOS
REPO = r"C:\Users\mrtim\Documents\family-hub"
for season, look, title in PICKS:
    out = Path(PHOTOS) / season / f"{look}.jpg"
    if out.exists() and out.stat().st_size > 0:
        continue
    for attempt in range(1, 7):
        r = subprocess.run([sys.executable, "scripts/season-photo-search.py", "fetch", "commons:" + title, "--out", str(out)],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode == 0:
            print("ok", look, flush=True)
            time.sleep(15)
            break
        print("retry", look, attempt, (r.stderr or r.stdout).strip()[:90], flush=True)
        time.sleep(30 * attempt)
    else:
        print("FAILED", look, flush=True)
```
Run in the background: `cd $W && PYTHONUTF8=1 $W/venv/Scripts/python fetch_all.py > fetch.log 2>&1` (run_in_background; about 10 to 20 minutes). Expected: no `FAILED` line, 29 files `<season>/<look>.jpg`, no `.part` files. Re-run it for any that failed.

- [ ] **Step 4: Prove the licences, file by file**

Create `$W\verify_licences.py`. For each pick it reads the Commons description and licence, and applies these rules: an Unsplash mirror (wikitext contains `{{Unsplash}}`) passes only if the Unsplash image id in the wikitext (`photo-<13 digits>` is a Unix-millisecond upload time) or a Wayback capture date (`date=20YYMMDD...`) is before 2017-06-01; the Pixabay photo passes only if the Commons licence is CC0 and the Commons upload timestamp is before 2019-01-09 (Pixabay's switch away from CC0); every other photo passes only if the Commons `LicenseShortName` starts with `CC0` or `Public domain`. It prints a table, writes `licences.json`, and exits non-zero if anything is REVIEW.

```python
import datetime as dt, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from picks import PICKS

UA = {"User-Agent": "family-hub-seasons/1.0 (dapperdodger)"}
UNSPLASH_CUTOFF = dt.datetime(2017, 6, 1)
PIXABAY_CUTOFF = dt.datetime(2019, 1, 9)
OPERATOR_ACCEPTED = {"julyfourth-fireworks": "operator kept it 2026-10-07: NPS photo gallery, author not recorded, PD-USGov-NPS plus a stray cc-by-sa-2.0 tag"}

def page(title):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": title, "prop": "imageinfo|revisions", "iiprop": "timestamp|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|DateTimeOriginal", "rvprop": "content", "rvslots": "main"})
    for wait in (0, 10, 30, 60, 120):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
                return list(json.load(r)["query"]["pages"].values())[0]
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise SystemExit("rate limited")

out, bad = {}, 0
for season, look, title in PICKS:
    p = page(title)
    text = p["revisions"][0]["slots"]["main"]["*"]
    ii = p["imageinfo"][0]
    lic = ii["extmetadata"]["LicenseShortName"]["value"]
    uploaded = dt.datetime.strptime(ii["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
    row = {"licence": lic, "uploaded": uploaded.date().isoformat(), "verdict": "REVIEW", "evidence": ""}
    free = lic.startswith("CC0") or lic.startswith("Public domain")
    if "{{Unsplash" in text:
        ms = re.search(r"photo-(\d{13})", text)
        way = re.findall(r"date=(20\d{6})", text)
        when = dt.datetime.utcfromtimestamp(int(ms.group(1)) / 1000) if ms else None
        wb = min((dt.datetime.strptime(d, "%Y%m%d") for d in way), default=None)
        proof = [x for x in (when, wb) if x]
        row["unsplash_year"] = (min(proof).year if proof else uploaded.year)
        if free and proof and min(proof) < UNSPLASH_CUTOFF:
            row["verdict"] = "PASS"
            row["evidence"] = "unsplash id time " + (when.date().isoformat() if when else "-") + ", wayback " + (wb.date().isoformat() if wb else "-")
        else:
            row["evidence"] = "no proof it was on Unsplash before 2017-06-01"
    elif "pixabay" in text.lower():
        if lic.startswith("CC0") and uploaded < PIXABAY_CUTOFF:
            row["verdict"] = "PASS"
            row["evidence"] = f"Pixabay, CC0, uploaded to Commons {uploaded.date()} (before Pixabay's 2019 licence change)"
        else:
            row["evidence"] = "Pixabay photo that may not be CC0"
    elif free:
        row["verdict"] = "PASS"
        row["evidence"] = "Commons licence " + lic
    if look in OPERATOR_ACCEPTED and free:
        row["verdict"] = "PASS"
        row["evidence"] = OPERATOR_ACCEPTED[look]
    out[look] = row
    bad += row["verdict"] != "PASS"
    print(f'{row["verdict"]:6} {look:28} {lic:22} {row["evidence"]}', flush=True)
json.dump(out, open("licences.json", "w"), indent=1)
sys.exit(1 if bad else 0)
```
Run: `cd $W && PYTHONUTF8=1 $W/venv/Scripts/python verify_licences.py`. Expected: 29 `PASS` lines, exit 0. **If any line says `REVIEW`, STOP for that look: do not prepare or commit it; report the line to the operator and ask for a replacement** (the sheets in `$W\harvest\hol-<season>*.html` have the other candidates).

- [ ] **Step 5: Prepare the photos**

```
cd /c/Users/mrtim/Documents/family-hub
for each (season, look) in picks.py:  $W/venv/Scripts/python scripts/prep-season-photo.py "$PHOTOS/<season>/<look>.jpg" <look>
```
(a loop in a one-off script that imports `PICKS` is fine). Expected: 29 lines `<look>.webp  2560xN  <size> KB`. Any file over 2.6 MB: rerun that one with `--quality 76`. Record the 29 sizes and their total in the ledger. Check: `ls src/family_hub/web/static/seasons/*.webp | wc -l` is 29 + the 17 existing = 46.

- [ ] **Step 6: Credit them**

Create `$W\credits_rows.py`. It writes the 29 rows under `## Photos` in `CREDITS.md`, after the last existing photo row, in the existing column format, with LF endings. The table `LOOKS` is (look id, display title, creator, kind); `kind` picks the licence text; Unsplash rows get the year from `licences.json`:

```python
import json, re
from pathlib import Path
from picks import PICKS
from edit import edit, sub

CC0 = "[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)"
KIND = {
    "cc0": CC0,
    "unsplash": CC0 + " (published under Unsplash's CC0 terms, before its 2017 licence change)",
    "pd-gov": "Public domain (work of the US federal government)",
    "pd-self": "Public domain (released by its author)",
    "pd-1963": "Public domain (published in 1963 without a copyright notice, so it entered the public domain; posted by the National Park Service)",
}
LOOKS = [  # look id, display title, creator, kind, extra note after the source link
    ("thanksgiving-pumpkins", "Cucurbita 2011 G1", "George Chernilevsky", "pd-self", ""),
    ("thanksgiving-cranberries", "Cranberrys beim Ernten", "Keith Weller, USDA-ARS", "pd-gov", ""),
    ("thanksgiving-pumpkin-bowl", "2016 USDA Farmers Market (20161021-AMS-LSC-0081)", "USDA", "pd-gov", ""),
    ("thanksgiving-turkey", "Wild Turkey", "U.S. Fish and Wildlife Service, Midwest Region", "pd-gov", ""),
    ("christmas-santa", "A figure of Christmas", "Caleb Woods", "unsplash", ""),
    ("christmas-village", "Christmas holiday model", "Nathan Anderson", "unsplash", ""),
    ("christmas-snowmen", "Snowmen at Christmas", "Jeffrey Wegrzyn", "unsplash", ""),
    ("newyears-sparkler", "Mumbai sparkler", "Bhushan Sadani", "unsplash", ""),
    ("newyears-fireworks", "Fireworks over water", "Adam Whitlock", "unsplash", ""),
    ("newyears-champagne", "Champagne glasses", "Myriam Zilles", "cc0", " (from Pixabay, 2016, when Pixabay images were CC0)"),
    ("mlkday-march", "Martin Luther King Jr National Historic Site (March on Washington, 28 August 1963)", "National Park Service", "pd-1963", ""),
    ("valentines-bouquet", "Pink rose bouquet", "Caroline Attwood", "unsplash", ""),
    ("valentines-tulips", "Luxurious red tulips", "Benny Jackson", "unsplash", ""),
    ("valentines-rose", "Red rose in macro", "Meredith Whitman", "unsplash", ""),
    ("stpatricks-countryside", "Green countryside", "Oliver Olah", "unsplash", ""),
    ("stpatricks-bay", "Coastal bay cliffs", "Thomas Kelley", "unsplash", ""),
    ("stpatricks-clover", "Four-leaf Clover (Trifolium repens)", "KEBman", "pd-self", ""),
    ("easter-eggs", "Easter candy", "Tim Gouw", "unsplash", ""),
    ("easter-ducklings", "Duckling chicks", "Roksolana Zasiadko", "unsplash", ""),
    ("easter-rabbit", "Brown rabbit green grass", "Ray Hennessy", "unsplash", ""),
    ("mothersday-tulips", "Tulip bouquet, Vienna", "G\u00e1bor Juh\u00e1sz", "unsplash", ""),
    ("mothersday-blossom", "Blossom, Austria, spring", "Markus Clemens", "unsplash", ""),
    ("mothersday-wildflowers", "Bouquet of wildflowers, Ehrenbach", "Gerda Arendt", "cc0", ""),
    ("fathersday-fjord", "Nordfjordeid river sunset", "Steinar Engeland", "unsplash", ""),
    ("fathersday-jeep", "Retro jeep with canoe on roof", "Quinn Nietfeld", "unsplash", ""),
    ("fathersday-campfire", "Campfire Cooking", "Evan Kirby", "unsplash", ""),
    ("julyfourth-fireworks", "Independence Day Fireworks in the National Mall", "National Park Service, National Mall and Memorial Parks (author not recorded)", "pd-gov",
     " (NPS photo gallery; the Commons page also carries a CC-BY-SA 2.0 tag, but the work is a federal photograph)"),
    ("julyfourth-sparkler", "American Flag and Sparkler", "Trent Yarnell", "unsplash", ""),
    ("julyfourth-flag", "American Flag On A Pole", "Caleb Woods", "unsplash", ""),
]
lic = json.load(open(Path(__file__).parent / "licences.json", encoding="utf-8"))
titles = {look: t for _, look, t in PICKS}
rows = []
for look, title, creator, kind, note in LOOKS:
    url = "https://commons.wikimedia.org/wiki/" + titles[look].replace(" ", "_")
    extra = note
    if kind == "unsplash":
        extra = f" (from Unsplash, {lic[look]['unsplash_year']})"
    rows.append(f'| `{look}.webp` | "{title}", {creator} | [Wikimedia Commons]({url}){extra} | {KIND[kind]} |')
assert len(rows) == 29 and {r[0] for r in LOOKS} == {p[1] for p in PICKS}

def add(s):
    last = list(re.finditer(r"^\| `[a-z0-9-]+\.webp`.*$", s, re.M))[-1]
    return s[:last.end()] + "\n" + "\n".join(rows) + s[last.end():]

path = r"C:\Users\mrtim\Documents\family-hub\src\family_hub\web\static\seasons\CREDITS.md"
data = open(path, "rb").read().replace(b"\r", b"").decode("utf-8")      # CREDITS.md is LF only (a test enforces it)
open(path, "wb").write(add(data).encode("utf-8"))
print("rows added:", len(rows))
```
Run it, then `PYTHONPATH=src TZ=UTC PYTHONUTF8=1 $PY -m pytest tests/test_static.py -q -k "credit or season_art or line_endings"`. Expected: `rows added: 29`, the credit guards pass. Open the CREDITS.md rows once and read three of them (an Unsplash one, `mlkday-march`, `julyfourth-fireworks`) for sense.

- [ ] **Step 7: Commit**

CHANGELOG: add under `## [Unreleased]` > `### Added`: `- Seasons: the artwork for the ten holidays (29 photos, all public domain or CC0, each licence checked and credited); nothing paints them yet.`

```bash
git add src/family_hub/web/static/seasons CHANGELOG.md
git commit -m "feat: artwork for the holiday looks (nothing paints it yet)"
```

---

### Task 2: Five new season marks

**Files:**
- Create: `src/family_hub/web/static/seasons/mark-heart.svg`, `mark-egg.svg`, `mark-mountain.svg`, `mark-star.svg`, `mark-candle.svg`
- Modify: `src/family_hub/web/static/seasons/CREDITS.md` (LF only), `src/family_hub/web/static/styles.css`, `CHANGELOG.md`

**Interfaces:**
- Consumes: the `.season-mark` / `.look-mark` mask mechanism and the existing rule shape `[data-look^="winter-"] .season-mark, .look-swatch[data-look^="winter-"] .look-mark { --mark: url("seasons/mark-snowflake.svg"); }`.
- Produces: a mark rule for each of the ten holiday prefixes. Reused files: `leaf-maple.svg` (thanksgiving), `mark-snowflake.svg` (christmas), `shape-spark.svg` (newyears), `shape-clover.svg` (stpatricks), `mark-blossom.svg` (mothersday). New: heart (valentines), egg (easter), mountain (fathersday), star (julyfourth), candle (mlkday).

- [ ] **Step 1: Failing test first.** The existing guard `test_season_art_files_exist_and_are_credited` fails on any file in `seasons/` without a credit row. Create the five SVGs (Write tool, one single-colour path each, `viewBox="0 0 100 100"`, every shape inside the box, no scene, no text):

`mark-heart.svg`:
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="#000" d="M50 88C14 60 8 38 8 28 8 15 18 8 29 8c9 0 17 5 21 13 4-8 12-13 21-13 11 0 21 7 21 20 0 10-6 32-42 60z"/></svg>
```
`mark-egg.svg` (an egg with a zig-zag band cut out of it, even-odd):
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="#000" fill-rule="evenodd" d="M50 6C74 6 88 40 88 62c0 20-16 32-38 32S12 82 12 62C12 40 26 6 50 6zM20 56l10-9 10 9 10-9 10 9 10-9 10 9v10l-10-9-10 9-10-9-10 9-10-9-10 9z"/></svg>
```
`mark-mountain.svg`:
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="#000" d="M4 84 34 26l16 28 16-36 30 66z"/></svg>
```
`mark-star.svg` (a five-point star, centre 50 53, radii 44 and 18):
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="#000" d="M50 9 60.6 38.4 91.8 39.4 67.1 58.6 75.9 88.6 50 71 24.1 88.6 32.9 58.6 8.2 39.4 39.4 38.4z"/></svg>
```
`mark-candle.svg` (a flame over a candle):
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="#000" d="M50 5C60 20 66 28 66 38c0 9-7 15-16 15s-16-6-16-15C34 28 40 20 50 5z"/><rect fill="#000" x="40" y="58" width="20" height="36" rx="3"/></svg>
```
Run `PYTHONPATH=src TZ=UTC PYTHONUTF8=1 $PY -m pytest tests/test_static.py -q -k season_art`. Expected: FAIL naming the five uncredited files.

- [ ] **Step 2: Credit them** (GREEN). Append under the `## Shapes` table (after the `mark-sun.svg` row, LF only) five rows in the existing format:

```
| `mark-heart.svg` | Self-made abstract heart (two lobes and a point), no source image | CC0 |
| `mark-egg.svg` | Self-made abstract egg (an oval with a zig-zag band), no source image | CC0 |
| `mark-mountain.svg` | Self-made abstract mountain (two peaks), no source image | CC0 |
| `mark-star.svg` | Self-made abstract five-point star, no source image | CC0 |
| `mark-candle.svg` | Self-made abstract candle (a flame over a stem), no source image | CC0 |
```
Re-run the test; expected PASS.

- [ ] **Step 3: The mark rules.** In `styles.css`, next to the existing `[data-look^="summer-"] .season-mark` rule, add:

```css
[data-look^="thanksgiving-"] .season-mark,
.look-swatch[data-look^="thanksgiving-"] .look-mark { --mark: url("seasons/leaf-maple.svg"); }
[data-look^="christmas-"] .season-mark,
.look-swatch[data-look^="christmas-"] .look-mark { --mark: url("seasons/mark-snowflake.svg"); }
[data-look^="newyears-"] .season-mark,
.look-swatch[data-look^="newyears-"] .look-mark { --mark: url("seasons/shape-spark.svg"); }
[data-look^="mlkday-"] .season-mark,
.look-swatch[data-look^="mlkday-"] .look-mark { --mark: url("seasons/mark-candle.svg"); }
[data-look^="valentines-"] .season-mark,
.look-swatch[data-look^="valentines-"] .look-mark { --mark: url("seasons/mark-heart.svg"); }
[data-look^="stpatricks-"] .season-mark,
.look-swatch[data-look^="stpatricks-"] .look-mark { --mark: url("seasons/shape-clover.svg"); }
[data-look^="easter-"] .season-mark,
.look-swatch[data-look^="easter-"] .look-mark { --mark: url("seasons/mark-egg.svg"); }
[data-look^="mothersday-"] .season-mark,
.look-swatch[data-look^="mothersday-"] .look-mark { --mark: url("seasons/mark-blossom.svg"); }
[data-look^="fathersday-"] .season-mark,
.look-swatch[data-look^="fathersday-"] .look-mark { --mark: url("seasons/mark-mountain.svg"); }
[data-look^="julyfourth-"] .season-mark,
.look-swatch[data-look^="julyfourth-"] .look-mark { --mark: url("seasons/mark-star.svg"); }
```
Run the static suite and `test_no_house_data`; expected all pass (the existing guard that every `url("seasons/...")` in the CSS names a real file passes because every referenced file exists). **Mutation-check:** point one rule at a missing file (`mark-hart.svg`), expect a failure, restore.

- [ ] **Step 4: Commit.** CHANGELOG `### Added`: `- Seasons: five new season marks (heart, egg, mountain, star, candle) for the holidays coming next; nothing uses them yet.`

```bash
git add src tests CHANGELOG.md
git commit -m "feat: season marks for the holidays"
```

---

### Task 3: The look tokens (photo, focal point, accent, leaf colours, petal tints)

**Files:**
- Modify: `src/family_hub/web/static/styles.css`, `tests/test_static.py`, `CHANGELOG.md`
- Scratch only: `$W\build_looks_css.py`, `$W\looks_table.json`

**Interfaces:**
- Consumes: the 29 prepared WebPs (Task 1), the dark+light block shape and the guards `test_every_look_sets_its_photo_and_accent_and_leaves_the_theme_alone` / `_SEASON_SHAPE_TOKENS` / `_PER_LOOK_SHAPES` in `tests/test_static.py`.
- Produces: for each of the 29 looks, `:root[data-look="X"][data-theme][data-accent], .look-swatch[data-look="X"] { --accent --accent-ink --accent-soft --sn-scene --sn-pos }` then the Light/Soft block with a deeper accent; Thanksgiving looks also set `--sn-leaf-1..4`; shared `:root[data-look^="valentines-"|"easter-"|"mothersday-"]` blocks set the petal tints. (The guards only run for looks the registry lists, which is Task 5; so this task carries its own test.)

- [ ] **Step 1: Write the failing test.** In `tests/test_static.py` add a literal list and the test (RED: no CSS yet):

```python
HOLIDAY_LOOKS = [
    "thanksgiving-pumpkins", "thanksgiving-cranberries", "thanksgiving-pumpkin-bowl", "thanksgiving-turkey",
    "christmas-santa", "christmas-village", "christmas-snowmen",
    "newyears-sparkler", "newyears-fireworks", "newyears-champagne",
    "mlkday-march",
    "valentines-bouquet", "valentines-tulips", "valentines-rose",
    "stpatricks-countryside", "stpatricks-bay", "stpatricks-clover",
    "easter-eggs", "easter-ducklings", "easter-rabbit",
    "mothersday-tulips", "mothersday-blossom", "mothersday-wildflowers",
    "fathersday-fjord", "fathersday-jeep", "fathersday-campfire",
    "julyfourth-fireworks", "julyfourth-sparkler", "julyfourth-flag",
]


def test_every_holiday_look_is_styled_before_the_registry_lists_it():
    """The registry-driven guards only look at looks theme.js lists; this one pins the 29 holiday looks'
    CSS and photos on their own, so a block can never go missing between the art and the registry."""
    assert len(HOLIDAY_LOOKS) == 29
    for look in HOLIDAY_LOOKS:
        assert f':root[data-look="{look}"][data-theme][data-accent]' in CSS, f"{look} has no dark-theme block"
        assert f':root[data-look="{look}"][data-accent]:is([data-theme="light"],[data-theme="soft"])' in CSS, f"{look} has no light-theme block"
        assert f'--sn-scene:url("seasons/{look}.webp")' in CSS, f"{look} never paints its photo"
        assert (STATIC / "seasons" / f"{look}.webp").is_file(), f"missing {look}.webp"
```
Run `-k holiday_look`. Expected: FAIL naming `thanksgiving-pumpkins`.

- [ ] **Step 2: Extend the shape-token tables.** In `tests/test_static.py` (the `_SEASON_SHAPE_TOKENS` dict and `_PER_LOOK_SHAPES`), add every holiday prefix; every key must exist or the registry guard raises `StopIteration`:

```python
    "thanksgiving-": ["--sn-leaf-1", "--sn-leaf-2", "--sn-leaf-3", "--sn-leaf-4"],
    "christmas-": [],                     # white snow
    "newyears-": [],                      # gold sparkle (the drift's own colours)
    "mlkday-": [],                        # photo only
    "valentines-": ["--sn-petal-1", "--sn-petal-2"],
    "stpatricks-": [],                    # green clovers (the drift's own colours)
    "easter-": ["--sn-petal-1", "--sn-petal-2"],
    "mothersday-": ["--sn-petal-1", "--sn-petal-2"],
    "fathersday-": [],                    # photo only
    "julyfourth-": [],                    # gold sparkle
```
and `_PER_LOOK_SHAPES = ("fall-", "spring-", "thanksgiving-")` (Thanksgiving's leaf colours are picked per photo, like fall's). The three petal seasons use ONE shared block each (like Halloween), not per-look tokens.

- [ ] **Step 3: The accent chooser and CSS generator.** Create `$W\build_looks_css.py` (Write tool). It reads each prepared WebP, takes its most saturated mid-tone as the look's hue, derives the lighter dark-theme accent and a deeper light-theme accent that reaches 4.6:1 on both `#FFFFFF` and `#F7F3EB` (computed), the ink, the soft tint and (for Thanksgiving) four leaf colours; a grey photo (MLK Day) takes a warm-gold hue instead. It writes the blocks into `styles.css` before the Halloween shared block and prints a table:

```python
import colorsys, json, re
from pathlib import Path
from PIL import Image
from edit import edit, sub

REPO = Path(r"C:\Users\mrtim\Documents\family-hub")
STATIC = REPO / "src" / "family_hub" / "web" / "static"
SURFACES = [(255, 255, 255), (247, 243, 235)]          # the Light and Soft surfaces

def lin(c):
    c /= 255
    return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4

def lum(c):
    return .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2])

def contrast(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + .05) / (lo + .05)

def hx(c):
    return "#%02X%02X%02X" % tuple(round(x) for x in c)

def rgba(c, a):
    return "rgba(%d,%d,%d,%s)" % (*(round(x) for x in c), a)

def accents(path, hue=None):
    im = Image.open(path).convert("RGB")
    im.thumbnail((240, 240))
    q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    pal, total, best = q.getpalette(), im.width * im.height, None
    for count, idx in q.getcolors():
        r, g, b = pal[idx * 3: idx * 3 + 3]
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l < .15 or l > .88:
            continue
        score = s * (1 - abs(l - .5)) * (count / total) ** .5
        if best is None or score > best[0]:
            best = (score, h, s)
    _, h, s = best or (0, .1, 0)
    if hue is not None or s < .2:                    # a grey photo has no hue of its own
        h, s = (hue if hue is not None else .1), .7
    s = min(max(s, .55), .9)
    dark = tuple(x * 255 for x in colorsys.hls_to_rgb(h, .66, s))
    light = None
    for l100 in range(45, 8, -1):
        c = tuple(x * 255 for x in colorsys.hls_to_rgb(h, l100 / 100, s))
        if min(contrast(c, g) for g in SURFACES) >= 4.6:
            light = c
            break
    assert light, path
    dark_ink = (27, 20, 5)
    ink = dark_ink if contrast(dark, dark_ink) >= 7 else (255, 255, 255)
    leaves = [tuple(x * 255 for x in colorsys.hls_to_rgb((h + dh) % 1, ll, s))
              for dh, ll in ((0, .55), (.03, .64), (-.03, .48), (.06, .72))]
    return dict(dark=dark, ink=ink, light=light, leaves=leaves)

# id, comment label, focal point, hue override (None = from the photo)
LOOKS = [
    ("thanksgiving-pumpkins", "Heirloom Pumpkins: blue, grey and orange pumpkins on the grass (George Chernilevsky, public domain)", "center 50%", None),
    ("thanksgiving-cranberries", "Cranberry Harvest: a cranberry bog at harvest (Keith Weller, USDA-ARS, public domain)", "center 45%", None),
    ("thanksgiving-pumpkin-bowl", "Pumpkin Bowl: a bowl of pumpkin at the farmers market (USDA, public domain)", "center 55%", None),
    ("thanksgiving-turkey", "Wild Turkey: a wild turkey on the rocks (U.S. Fish and Wildlife Service, public domain)", "center 40%", None),
    ("christmas-santa", "Santa Lights: a Santa figure among coloured lights (Caleb Woods, CC0)", "center 45%", None),
    ("christmas-village", "Gingerbread Village: a tiny gingerbread village glowing in the dark (Nathan Anderson, CC0)", "center 45%", None),
    ("christmas-snowmen", "Snowmen: two snowmen among warm lights (Jeffrey Wegrzyn, CC0)", "center 55%", None),
    ("newyears-sparkler", "Sparkler: a sparkler throwing light in the dark (Bhushan Sadani, CC0)", "center 40%", None),
    ("newyears-fireworks", "Fireworks over Water: fireworks over dark water (Adam Whitlock, CC0)", "center 45%", None),
    ("newyears-champagne", "Champagne: two champagne coupes on black (Myriam Zilles, CC0)", "center 50%", None),
    ("mlkday-march", "March on Washington: Dr. King greeting the crowd, 28 August 1963 (National Park Service, public domain)", "center 40%", 0.11),
    ("valentines-bouquet", "Pink Bouquet: pale pink roses (Caroline Attwood, CC0)", "center 45%", None),
    ("valentines-tulips", "Red Tulips: red tulips in warm dim light (Benny Jackson, CC0)", "center 50%", None),
    ("valentines-rose", "Red Rose: a single red rose up close (Meredith Whitman, CC0)", "center 50%", None),
    ("stpatricks-countryside", "Green Countryside: bright green fields and two big trees (Oliver Olah, CC0)", "center 55%", None),
    ("stpatricks-bay", "Coastal Bay: green cliffs around a quiet bay (Thomas Kelley, CC0)", "center 55%", None),
    ("stpatricks-clover", "Four-Leaf Clover: a four-leaf clover in a patch of clover (KEBman, public domain)", "center 50%", None),
    ("easter-eggs", "Easter Eggs: foil-wrapped chocolate eggs (Tim Gouw, CC0)", "center 50%", None),
    ("easter-ducklings", "Ducklings: a huddle of yellow ducklings (Roksolana Zasiadko, CC0)", "center 50%", None),
    ("easter-rabbit", "Brown Rabbit: a brown rabbit in green grass (Ray Hennessy, CC0)", "center 50%", None),
    ("mothersday-tulips", "Tulip Bouquet: a mass of tulips in every colour (Gabor Juhasz, CC0)", "center 50%", None),
    ("mothersday-blossom", "Spring Blossom: pink blossom against a blue sky (Markus Clemens, CC0)", "center 45%", None),
    ("mothersday-wildflowers", "Wildflower Bouquet: a loose bouquet of wildflowers (Gerda Arendt, CC0)", "center 50%", None),
    ("fathersday-fjord", "Fjord Sunset: a river at sunset in Nordfjordeid (Steinar Engeland, CC0)", "center 55%", None),
    ("fathersday-jeep", "Road Trip: a retro jeep with a canoe on the roof (Quinn Nietfeld, CC0)", "center 70%", None),
    ("fathersday-campfire", "Campfire Cooking: a hot dog over a campfire at sunset (Evan Kirby, CC0)", "center 50%", None),
    ("julyfourth-fireworks", "National Mall Fireworks: fireworks over the National Mall (National Park Service, public domain)", "center 55%", None),
    ("julyfourth-sparkler", "Flag and Sparkler: a sparkler in front of the flag (Trent Yarnell, CC0)", "center 45%", None),
    ("julyfourth-flag", "Flag on a Pole: a flag against a blue sky (Caleb Woods, CC0)", "center 40%", None),
]
PETALS = {   # one shared tint per petal season
    "valentines": ("#F9B4C2", "#D83A55"),
    "easter": ("#FFF1A8", "#F4A7D0"),
    "mothersday": ("#FBD0DE", "#EE8DB0"),
}

blocks, table = [], {}
for look, label, pos, hue in LOOKS:
    a = accents(STATIC / "seasons" / f"{look}.webp", hue)
    table[look] = {k: (hx(v) if k != "leaves" else [hx(c) for c in v]) for k, v in a.items()}
    leaf = ""
    if look.startswith("thanksgiving-"):
        l1, l2, l3, l4 = (hx(c) for c in a["leaves"])
        leaf = f"  --sn-leaf-1:{l1}; --sn-leaf-2:{l2}; --sn-leaf-3:{l3}; --sn-leaf-4:{l4};\n"
    blocks.append(f'''/* ---- {label} ---- */
:root[data-look="{look}"][data-theme][data-accent],
.look-swatch[data-look="{look}"] {{
  --accent:{hx(a["dark"])}; --accent-ink:{hx(a["ink"])}; --accent-soft:{rgba(a["dark"], ".18")};
  --sn-scene:url("seasons/{look}.webp"); --sn-pos:{pos};
{leaf}}}
:root[data-look="{look}"][data-accent]:is([data-theme="light"],[data-theme="soft"]),
:root:is([data-theme="light"],[data-theme="soft"]) .look-swatch[data-look="{look}"] {{
  --accent:{hx(a["light"])}; --accent-ink:#FFFFFF; --accent-soft:{rgba(a["light"], ".13")};
}}
''')
shared = "".join(f'''/* ---- {s}: the petals every {s}-* look drifts ---- */
:root[data-look^="{s}-"],
.look-swatch[data-look^="{s}-"] {{ --sn-petal-1:{p1}; --sn-petal-2:{p2}; }}

''' for s, (p1, p2) in PETALS.items())

ANCHOR = "/* ---- Halloween: shared by every halloween-* look ----"
edit(STATIC / "styles.css", lambda s: sub(s, ANCHOR, shared + "\n".join(blocks) + "\n" + ANCHOR))
(Path(__file__).parent / "looks_table.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
for look, t in table.items():
    print(f'{look:28} dark {t["dark"]}  light {t["light"]}  ink {t["ink"]}')
```
Run: `cd $W && PYTHONUTF8=1 $W/venv/Scripts/python build_looks_css.py`. Expected: 29 lines, every `light` accent present. Spot check `looks_table.json`: the MLK accent is a gold (hue override), the others follow their photos.

- [ ] **Step 4: Run to verify GREEN.** `PYTHONPATH=src TZ=UTC PYTHONUTF8=1 $PY -m pytest tests/test_static.py tests/test_no_house_data.py -q`. Expected: all pass, including `test_every_holiday_look_is_styled_before_the_registry_lists_it` and `test_theme_tokens_base_on_root_no_override_orphans` (the petal tokens already have a `:root` base from PR 2).

- [ ] **Step 5: Commit.** CHANGELOG `### Added`: `- Seasons: the colours for the ten holiday seasons' 29 looks (a photo focal point and an accent taken from each photo, a deeper accent for Light and Soft, per-photo leaf colours for Thanksgiving and shared petal tints for Valentine's, Easter and Mother's Day); nothing paints them until the calendar lists them.`

```bash
git add src tests CHANGELOG.md
git commit -m "feat: colours and focal points for the 29 holiday looks"
```

---

### Task 4: Thanksgiving paints the fall leaves

**Files:**
- Modify: `src/family_hub/web/static/styles.css` (the three selectors near `:root[data-look^="fall-"] body > .season-fx .sn-leaves`), `tests/test_static.py` (`test_leaves_fall_at_two_depths`), `CHANGELOG.md`

**Interfaces:**
- Consumes: the leaf layers (`body > .season .sn-leaves` far set, `body > .season-fx .sn-leaves` near set, `.look-swatch .sn-leaves` in a Settings tile), shown today only for `fall-` looks; Lite already hides both layers (`LITE_COVERS` includes `sn-leaves`).
- Produces: the same layers shown for `thanksgiving-` looks, in the wall and in the tiles.

- [ ] **Step 1: Failing test.** In `test_leaves_fall_at_two_depths` loop over both prefixes (change the tuple of required selectors to cover `fall-` and `thanksgiving-`):

```python
    for pre in ("fall-", "thanksgiving-"):
        for sel in (f':root[data-look^="{pre}"] body > .season .sn-leaves',
                    f':root[data-look^="{pre}"] body > .season-fx .sn-leaves',
                    f'.look-swatch[data-look^="{pre}"] .sn-leaves'):
            assert sel in shown, f"{sel} is never shown"
```
Run `-k leaves_fall`. Expected: FAIL naming the `thanksgiving-` selector.

- [ ] **Step 2: Implement.** Replace the three-line selector group in `styles.css` with:

```css
:root[data-look^="fall-"] body > .season-fx .sn-leaves,
:root[data-look^="fall-"] body > .season .sn-leaves,
.look-swatch[data-look^="fall-"] .sn-leaves,
:root[data-look^="thanksgiving-"] body > .season-fx .sn-leaves,
:root[data-look^="thanksgiving-"] body > .season .sn-leaves,
.look-swatch[data-look^="thanksgiving-"] .sn-leaves { display: block; }
```
Run the static suite. Expected: PASS. **Mutation-check:** delete one `thanksgiving-` selector, expect FAIL, restore (`cmp`).

- [ ] **Step 3: Commit.** CHANGELOG `### Added`: `- Seasons: Thanksgiving looks drift the same falling leaves as Fall (and Lite keeps them still, like Fall's).`

```bash
git add src tests CHANGELOG.md
git commit -m "feat: Thanksgiving paints the fall leaves"
```

---

### Task 5: The registry and the calendar

**Files:**
- Create: `tests/js/fixtures/make_season_calendar.py`, `tests/js/fixtures/season-calendar.json`, `tests/test_season_calendar_fixture.py`
- Modify: `src/family_hub/web/static/theme.js` (`SEASONS`), `tests/js/seasons.test.mjs`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `WINDOWS.easter / mothersDay / fathersDay / mlkDay / thanksgiving` (already in theme.js), the registry fields `id, name, from, to | window + when, drift, looks[{id,name,blurb,credit,default}]`, the look CSS and photos from Tasks 1 to 4, `T.seasonFor(date)` and `T.seasonOutlook(date)` from `window.FH_SEASON_TOOLS`.
- Produces: the registry in the spec's order with 29 new looks (46 in all).

- [ ] **Step 1: The independent calendar oracle and fixture.** Create `tests/js/fixtures/make_season_calendar.py` (this knows the calendar rules, not theme.js; the JSON it writes is what the JS test checks):

```python
"""Regenerates season-calendar.json: which season must paint on the edge days of every window.

An independent oracle: it re-derives Easter (the Gregorian computus) and the nth-weekday holidays in Python and
applies the registry ORDER from the spec, so the JS test cannot just mirror theme.js.
Run:  python tests/js/fixtures/make_season_calendar.py
tests/test_season_calendar_fixture.py fails if the committed JSON is stale.
"""
import datetime as dt
import json
from pathlib import Path

D = dt.timedelta
YEARS = (2008, 2026, 2027, 2028, 2030, 2038)   # 2008/2038 are the earliest/latest Easters; 2028 is a leap year; 2030's Thanksgiving touches Dec 1
ORDER = ["newyears", "christmas", "mlkday", "valentines", "winter", "stpatricks", "easter", "mothersday", "spring",
         "fathersday", "julyfourth", "summer", "halloween", "thanksgiving", "fall"]


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e, f = b // 4, b % 4, (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return dt.date(y, month, ((h + l - 7 * m + 114) % 31) + 1)


def nth(y, month, weekday_sunday0, n):
    first = dt.date(y, month, 1)
    return first + D(days=(weekday_sunday0 - (first.weekday() + 1) % 7) % 7 + 7 * (n - 1))


def window(sid, y):
    mom, dad, mlk, thx = nth(y, 5, 0, 2), nth(y, 6, 0, 3), nth(y, 1, 1, 3), nth(y, 11, 4, 4)
    return {
        "christmas": (dt.date(y, 12, 1), dt.date(y, 12, 26)),
        "valentines": (dt.date(y, 2, 1), dt.date(y, 2, 14)),
        "stpatricks": (dt.date(y, 3, 1), dt.date(y, 3, 17)),
        "julyfourth": (dt.date(y, 6, 25), dt.date(y, 7, 4)),
        "spring": (dt.date(y, 3, 1), dt.date(y, 5, 31)),
        "summer": (dt.date(y, 6, 1), dt.date(y, 8, 31)),
        "halloween": (dt.date(y, 10, 1), dt.date(y, 10, 31)),
        "fall": (dt.date(y, 9, 1), dt.date(y, 11, 30)),
        "easter": (easter(y) - D(14), easter(y) + D(1)),
        "mothersday": (mom - D(6), mom),
        "fathersday": (dad - D(3), dad),
        "mlkday": (mlk - D(3), mlk),
        "thanksgiving": (thx - D(10), thx + D(3)),
    }[sid]


def holds(sid, d):
    if sid == "newyears":
        return (d.month == 12 and d.day >= 27) or (d.month == 1 and d.day <= 2)
    if sid == "winter":
        return d.month in (12, 1, 2)
    a, b = window(sid, d.year)
    return a <= d <= b


def season(d):
    return next(s for s in ORDER if holds(s, d))


def rows():
    out = set()
    for y in YEARS:
        for sid in ("christmas", "mlkday", "valentines", "stpatricks", "easter", "mothersday", "fathersday", "julyfourth", "thanksgiving"):
            a, b = window(sid, y)
            for d in (a - D(1), a, b, b + D(1)):
                out.add((d.isoformat(), season(d)))
        for md in ((12, 26), (12, 27), (12, 31), (1, 1), (1, 2), (1, 3), (2, 28), (3, 1), (5, 31), (6, 1), (8, 31),
                   (9, 1), (9, 30), (10, 1), (10, 31), (11, 1), (11, 30)):
            d = dt.date(y, *md)
            out.add((d.isoformat(), season(d)))
    out.add(("2028-02-29", season(dt.date(2028, 2, 29))))
    return [list(r) for r in sorted(out)]


if __name__ == "__main__":
    path = Path(__file__).with_name("season-calendar.json")
    path.write_text(json.dumps(rows(), indent=0) + "\n", encoding="utf-8")
    print(len(rows()), "rows ->", path)
```
Run it: `$PY tests/js/fixtures/make_season_calendar.py`. Expected: about 290 rows written. Create `tests/test_season_calendar_fixture.py`:

```python
import importlib.util
import json
from pathlib import Path

FIX = Path(__file__).parent / "js" / "fixtures"


def test_the_season_calendar_fixture_is_current():
    spec = importlib.util.spec_from_file_location("make_season_calendar", FIX / "make_season_calendar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert json.loads((FIX / "season-calendar.json").read_text(encoding="utf-8")) == mod.rows()
```
Expected: it passes. Sanity-read a few oracle rows: `2026-11-16` thanksgiving, `2026-11-30` fall, `2030-12-01` christmas, `2008-03-17` stpatricks, `2008-03-18` easter.

- [ ] **Step 2: Failing JS tests.** In `tests/js/seasons.test.mjs` add `import { dirname, join } from 'node:path'` if absent, and REPLACE the three PR 2 "the real registry: ..." tests (`every day of the year paints the season...`, `October lists Halloween and Fall now...`, `look ids are unique...`) with:

```js
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
  assert.deepEqual(Array.from(o.upcoming.map((s) => s.id)), ['thanksgiving', 'christmas', 'newyears']);
  assert.deepEqual(Array.from(o.rest.map((s) => s.id)),
    ['mlkday', 'valentines', 'winter', 'stpatricks', 'easter', 'mothersday', 'spring', 'fathersday', 'julyfourth', 'summer']);
});

test('the real registry: season and look ids, defaults, prefixes and the words moving seasons need', () => {
  const { win } = loadTheme();
  assert.deepEqual(Array.from(win.FH_SEASONS.map((s) => s.id)),
    ['newyears', 'christmas', 'mlkday', 'valentines', 'winter', 'stpatricks', 'easter', 'mothersday', 'spring',
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
  assert.equal(seen.size, 46);
  const counts = Object.fromEntries(win.FH_SEASONS.map((s) => [s.id, s.looks.length]));
  assert.deepEqual(counts, { newyears: 3, christmas: 3, mlkday: 1, valentines: 3, winter: 3, stpatricks: 3, easter: 3,
    mothersday: 3, spring: 3, fathersday: 3, julyfourth: 3, summer: 3, halloween: 5, thanksgiving: 4, fall: 3 });
  const drifts = Object.fromEntries(win.FH_SEASONS.map((s) => [s.id, s.drift || null]));
  assert.deepEqual(drifts, { newyears: 'sparkle', christmas: 'snow', mlkday: null, valentines: 'petal', winter: 'snow',
    stpatricks: 'clover', easter: 'petal', mothersday: 'petal', spring: 'petal', fathersday: null, julyfourth: 'sparkle',
    summer: 'firefly', halloween: null, thanksgiving: null, fall: null });
});
```
(`readFileSync`, `fileURLToPath` and `dirname/join` are already imported at the top of the file; keep `loadTheme`, `T` and `d`.) Run `TZ=UTC node --test tests/js/seasons.test.mjs`. Expected: FAIL (the registry has only five seasons).

- [ ] **Step 3: The registry.** Write `$W\reg_add.py` that inserts the entries at these anchors in `SEASONS` (`edit`/`sub` from `$W\edit.py`; the file is UTF-8, keep `á`, `ú` as real characters). Insert the BLOCK before the anchor line:

- before `    { id: "winter", name: "Winter"`: `newyears`, `christmas`, `mlkday`, `valentines`
- before `    { id: "spring", name: "Spring"`: `stpatricks`, `easter`, `mothersday`
- before `    { id: "summer", name: "Summer"`: `fathersday`, `julyfourth`
- before `    { id: "fall", name: "Fall"`: `thanksgiving`

```javascript
    { id: "newyears", name: "New Year's", from: [12, 27], to: [1, 2], drift: "sparkle", looks: [
      { id: "newyears-sparkler", name: "Sparkler", blurb: "A sparkler throwing light in the dark", credit: "Photo by Bhushan Sadani", default: true },
      { id: "newyears-fireworks", name: "Fireworks over Water", blurb: "Fireworks over dark water", credit: "Photo by Adam Whitlock" },
      { id: "newyears-champagne", name: "Champagne", blurb: "Two champagne coupes on black", credit: "Photo by Myriam Zilles" },
    ] },
    { id: "christmas", name: "Christmas", from: [12, 1], to: [12, 26], drift: "snow", looks: [
      { id: "christmas-santa", name: "Santa Lights", blurb: "A Santa figure among coloured lights", credit: "Photo by Caleb Woods", default: true },
      { id: "christmas-village", name: "Gingerbread Village", blurb: "A tiny gingerbread village glowing in the dark", credit: "Photo by Nathan Anderson" },
      { id: "christmas-snowmen", name: "Snowmen", blurb: "Two snowmen among warm lights", credit: "Photo by Jeffrey Wegrzyn" },
    ] },
    { id: "mlkday", name: "Martin Luther King Jr. Day", window: WINDOWS.mlkDay, when: "The long weekend of Martin Luther King Jr. Day", looks: [
      { id: "mlkday-march", name: "March on Washington", blurb: "Dr. King greeting the crowd, 28 August 1963", credit: "Photo from the National Park Service archive", default: true },
    ] },
    { id: "valentines", name: "Valentine's Day", from: [2, 1], to: [2, 14], drift: "petal", looks: [
      { id: "valentines-bouquet", name: "Pink Bouquet", blurb: "A bouquet of pale pink roses", credit: "Photo by Caroline Attwood", default: true },
      { id: "valentines-tulips", name: "Red Tulips", blurb: "Red tulips in warm, dim light", credit: "Photo by Benny Jackson" },
      { id: "valentines-rose", name: "Red Rose", blurb: "A single red rose up close", credit: "Photo by Meredith Whitman" },
    ] },
    { id: "stpatricks", name: "St Patrick's Day", from: [3, 1], to: [3, 17], drift: "clover", looks: [
      { id: "stpatricks-countryside", name: "Green Countryside", blurb: "Bright green fields and two big trees", credit: "Photo by Oliver Olah", default: true },
      { id: "stpatricks-bay", name: "Coastal Bay", blurb: "Green cliffs around a quiet bay", credit: "Photo by Thomas Kelley" },
      { id: "stpatricks-clover", name: "Four-Leaf Clover", blurb: "A four-leaf clover in a patch of clover", credit: "Photo by KEBman" },
    ] },
    { id: "easter", name: "Easter", window: WINDOWS.easter, when: "The two weeks before Easter, through Easter Monday", drift: "petal", looks: [
      { id: "easter-eggs", name: "Easter Eggs", blurb: "Foil-wrapped chocolate eggs in every colour", credit: "Photo by Tim Gouw", default: true },
      { id: "easter-ducklings", name: "Ducklings", blurb: "A huddle of yellow ducklings", credit: "Photo by Roksolana Zasiadko" },
      { id: "easter-rabbit", name: "Brown Rabbit", blurb: "A brown rabbit in green grass", credit: "Photo by Ray Hennessy" },
    ] },
    { id: "mothersday", name: "Mother's Day", window: WINDOWS.mothersDay, when: "The week of Mother's Day", drift: "petal", looks: [
      { id: "mothersday-tulips", name: "Tulip Bouquet", blurb: "A mass of tulips in every colour", credit: "Photo by Gábor Juhász", default: true },
      { id: "mothersday-blossom", name: "Spring Blossom", blurb: "Pink blossom against a blue sky", credit: "Photo by Markus Clemens" },
      { id: "mothersday-wildflowers", name: "Wildflower Bouquet", blurb: "A loose bouquet of wildflowers", credit: "Photo by Gerda Arendt" },
    ] },
    { id: "fathersday", name: "Father's Day", window: WINDOWS.fathersDay, when: "The days leading up to Father's Day", looks: [
      { id: "fathersday-fjord", name: "Fjord Sunset", blurb: "A river at sunset in Nordfjordeid", credit: "Photo by Steinar Engeland", default: true },
      { id: "fathersday-jeep", name: "Road Trip", blurb: "A retro jeep with a canoe on the roof", credit: "Photo by Quinn Nietfeld" },
      { id: "fathersday-campfire", name: "Campfire Cooking", blurb: "A hot dog over a campfire at sunset", credit: "Photo by Evan Kirby" },
    ] },
    { id: "julyfourth", name: "Fourth of July", from: [6, 25], to: [7, 4], drift: "sparkle", looks: [
      { id: "julyfourth-fireworks", name: "National Mall Fireworks", blurb: "Fireworks over the National Mall", credit: "Photo by the National Park Service", default: true },
      { id: "julyfourth-sparkler", name: "Flag and Sparkler", blurb: "A sparkler in front of the flag", credit: "Photo by Trent Yarnell" },
      { id: "julyfourth-flag", name: "Flag on a Pole", blurb: "A flag against a blue sky", credit: "Photo by Caleb Woods" },
    ] },
    { id: "thanksgiving", name: "Thanksgiving", window: WINDOWS.thanksgiving, when: "The ten days before Thanksgiving, through the Sunday after", looks: [
      { id: "thanksgiving-pumpkins", name: "Heirloom Pumpkins", blurb: "Blue, grey and orange pumpkins on the grass", credit: "Photo by George Chernilevsky", default: true },
      { id: "thanksgiving-cranberries", name: "Cranberry Harvest", blurb: "A cranberry bog turned red at harvest", credit: "Photo by Keith Weller, USDA" },
      { id: "thanksgiving-pumpkin-bowl", name: "Pumpkin Bowl", blurb: "A warm bowl of pumpkin at the farmers market", credit: "Photo by USDA" },
      { id: "thanksgiving-turkey", name: "Wild Turkey", blurb: "A wild turkey on the rocks", credit: "Photo by the U.S. Fish and Wildlife Service" },
    ] },
```
(Insert the blocks in the order listed per anchor, each ending with a newline.) Also update the registry's order comment above `var SEASONS` only if it states a now-wrong order. Run `TZ=UTC node --test tests/js/*.test.mjs` and the static suite. Expected: all pass. Tests from PRs 1 and 2 that assumed the old five-season registry will fail here; update each to the smallest change that keeps its meaning and ledger the ruling. Known: in `tests/js/seasons.test.mjs`, `data-drift follows the painting season` asks about Dec 10 and expects Winter, but Christmas now wins Dec 1 to 26: ask about Jan 15 for Winter's snow and add a Dec 10 expectation of Christmas's snow (`christmas-santa`). Others (the Settings picker tests in `tests/js/hub-dom.test.mjs`, anything counting the registry's looks or tiles) show up as RED; fix them the same way.

- [ ] **Step 4: Mutation-check** (each must fail a test; restore and `cmp` after each): (a) swap `stpatricks` and `easter` in the registry (fixture, 2008); (b) move Christmas's end to `[12, 25]`; (c) delete mlkday's `when`; (d) change New Year's `from` to `[12, 28]`; (e) delete Easter's `drift`; (f) rename `thanksgiving-turkey`'s id to `thanksgiving-turkeyy` (CSS/photo guards); (g) remove one holiday look's dark token block from `styles.css` (the registry-driven guard); (h) set `--ink` in one holiday look block (theme-owned guard); (i) delete one holiday `CREDITS.md` row; (j) put a `\r\r\n` in `CREDITS.md`.

- [ ] **Step 5: Commit.** CHANGELOG `### Added`: `- Seasons: the ten holidays: New Year's (Dec 27 to Jan 2), Christmas (Dec 1 to 26), Martin Luther King Jr. Day, Valentine's Day (Feb 1 to 14), St Patrick's Day (Mar 1 to 17), Easter, Mother's Day, Father's Day, the Fourth of July (Jun 25 to Jul 4) and Thanksgiving, with 29 looks between them. Each one wins over the broad season it sits in. Turn Seasonal looks on in Settings and pick the photos you like.`

```bash
git add src tests CHANGELOG.md
git commit -m "feat: the ten holiday seasons and their calendar"
```

---

### Task 6: The visual gates

**Files:** none committed unless a fix is needed (each fix gets a test first where it can be tested, otherwise a ledgered eyeball fix).

- [ ] **Step 1: The matrix.** Start the demo wall (see Working environment). Create `$W\gen_matrix.py` (Write tool): for every one of the 29 looks and each of `light, soft, blue, grey, black`, a 1920x1080 scenario at `http://127.0.0.1:8199/?kiosk=1` whose `js` is `setTheme('<theme>'); setSeason('on'); var f=function(){var r=document.documentElement;r.setAttribute('data-look','<look>');r.setAttribute('data-drift','<kind>');}; f(); setInterval(f,30); new Promise(function(r){setTimeout(r,3500)})` (the kind is the season's drift from the registry: christmas `snow`, newyears and julyfourth `sparkle`, valentines/easter/mothersday `petal`, stpatricks `clover`, the rest `none`), `wait: 3500`, `settle: 800`, output `$W/shots/mx/<look>-<theme>.png`. Run `node shot.mjs mx.json` in the background (about 15 to 20 minutes for 145 shots). Then `$W\mx_mont.py` (Pillow) builds one montage per holiday: a row of five 360x203 theme tiles per look, stacked, saved as `$W/shots/mx/M-<season>.jpg`. **Read all ten montages** and note every look that fails the standard (text over the photo unreadable, the accent illegible on the glass, empty check rings or struck-through lines vanishing, the subject hidden behind a card column).
- [ ] **Step 2: Full-size spot checks** for the highest-risk looks, each at full size in Light and Soft (crop the left 1000x640 of the shot to read the chores card): `easter-eggs`, `newyears-champagne`, `thanksgiving-pumpkin-bowl`, `mlkday-march`, `mothersday-tulips`, `julyfourth-flag`, `christmas-snowmen`, `stpatricks-clover`, `valentines-rose`. Read the numbers as well: for each of these, the light accent against `#FFFFFF` and `#F7F3EB` from `looks_table.json` is at least 4.6:1.
- [ ] **Step 3: Motion.** Capture a Thanksgiving look (leaves drifting, near and far), `stpatricks-clover` (clovers visible on a clover photo but not busy), `newyears-fireworks` (gold sparkle on the dark photo), `julyfourth-flag` (sparkle on a daytime sky), `valentines-rose` (petals tinted red), and one of `mlkday-march` and `fathersday-jeep` (no drift).
- [ ] **Step 4: The rest of the checklist,** for at least one look per season: night (`document.body.classList.add('is-night')` re-asserted on an interval), Lite on (`setLite('on')`: no blur, no drift, no leaves, glass 86%), the phone at 390x844 and 360x780 (no sideways spill: `document.documentElement.scrollWidth` equals the window width; the gear popover; a two-digit hour), and the Settings page (`openOverlay('settings')`, open every `details.look-fold`, scroll to the first, capture; read all 46 tiles over three or four pages: each shows its photo, its mark and its resting drift, and the picker has three groups with Thanksgiving/Christmas/New Year's under "Coming up" in October and each moving season showing its `when` text). Seasons off: with the season pref off `data-look` is `none` and nothing paints; all new CSS is look-scoped, so there is nothing to compare.
- [ ] **Step 5: Fix what fails.** A focal point that hides the subject: change that look's `--sn-pos` in `styles.css`. An accent that is dim on the glass: re-run `build_looks_css.py`'s `accents()` with a different `hue` and edit that one block. A rule or selector problem gets a failing test first. Re-capture the affected looks and re-read them. Ledger every change (look, old value, new value, why).
- [ ] **Step 6: Commit any fixes,** one commit per concern with a CHANGELOG `### Fixed` bullet (`- Seasons: the <look> look's focal point keeps its subject clear of the cards.`).

---

### Task 7: Docs, the showcase image, full verification, review, PR

**Files:**
- Modify: `README.md`, `docs/seasonal-looks.md`, `CHANGELOG.md`
- Create: `docs/holidays.jpg`

- [ ] **Step 1: Docs.** README, in the **Seasonal looks** bullet: after the Winter/Spring/Summer sentence add a sentence listing the holidays with their dates and looks (Thanksgiving with the falling leaves, Christmas and New Year's, Martin Luther King Jr. Day, Valentine's Day, St Patrick's Day with drifting clovers, Easter, Mother's Day, Father's Day, the Fourth of July), say that the holiday wins over the broad season it sits in and that Thanksgiving week uses Thanksgiving's own look (not the device's Fall pick), and embed the new image under the existing one: `![Seasonal looks: the holidays](docs/holidays.jpg)`. `docs/seasonal-looks.md`: update **Shipped so far** (fall, Halloween, winter, spring, summer and the ten holidays, 15 seasons) and replace the "What's next" sentence with: other days (Memorial Day, Labor Day, Veterans Day, Presidents' Day) are out of scope until asked and follow the same recipe; fix the stale intro line ("a few leaves drift down") to say that each season has one gentle kind of motion. Also note in the standard that Pixabay photos are acceptable only if uploaded before 2019-01-09 and that Unsplash ones need the per-file pre-June-2017 proof (`$W\verify_licences.py` is the recipe).
- [ ] **Step 2: The showcase.** Compose `docs/holidays.jpg` (about 1932x726, JPEG quality 84, under 450 KB) as a 3x2 grid of 640x360 wall shots from the matrix, one per tile: `thanksgiving-pumpkins` (Soft), `christmas-snowmen` (Black), `easter-rabbit` (Light), `stpatricks-clover` (Grey), `julyfourth-fireworks` (Black), `mothersday-tulips` (Soft). Read the result once.
- [ ] **Step 3: Full verification.** `TZ=UTC node --test tests/js/*.test.mjs`; the full pytest (`> $W/final.txt`) and compare the failing test names with `$W/baseline-failures.txt` (no new failures); `test_no_house_data` after the commit (it reads tracked files only); check `git ls-files` shows no file over 2.6 MB under `static/seasons/`; record the 29 WebP sizes and their total; run `git diff --stat main...HEAD | tail -3`.
- [ ] **Step 4: Commit the docs** (CHANGELOG `### Added`: `- Docs: the README and the seasonal-looks standard describe the holidays, and a second showcase image shows six of them.`).
- [ ] **Step 5: Review.** A fresh-context review of the whole branch (dispatch the most capable model) with this plan's Review Focus verbatim, the ledger's `Ruling:` lines and the diff package from `review-package`. Apply Critical and Important findings in ONE fix pass (each fix RED then GREEN, then the whole suite); ledger the minors.
- [ ] **Step 6: Push and PR.** `git push -u origin feat/seasons-holidays`, then `gh pr create -R dapperdodger/family-hub --base main --head feat/seasons-holidays` with a body that has the table of the ten seasons (window, motion, looks), the licence evidence summary (20 Unsplash mirrors proven by upload time, Pixabay CC0 before 2019, the NPS fireworks provenance and the operator's decision, the 1963 MLK photograph's basis), the WebP total, the test counts and the deferred minors, ending with the attribution line from the session reminder.
