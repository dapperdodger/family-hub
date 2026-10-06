# Recipe browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native full-screen **Recipes** view (wall and phone) that lists the Mealie recipes as a photo grid with search, category chips and sort buttons, and opens one to read its ingredients, steps and notes, replacing the slow Mealie iframe behind the Dinner card's "Full screen" button.

**Architecture:** Two read-only, fail-soft endpoints on the existing Mealie proxy (`meals.py`/`app.py`): one returns every recipe summary in a single capped request, one returns a single recipe's detail; the photo proxy gains a `size` option with a larger thumbnail cache. The view is a new `recipes` overlay in `hub.js` with its own grid/detail navigation; search, category and sort run on the loaded list in pure functions in `common.js`. Typing redraws only the card area, never the search box, so the on-screen keyboard keeps focus.

**Tech Stack:** Python 3.13 / FastAPI / httpx / pytest (backend); vanilla JS (`hub.js`, `common.js`) with the repo's fake-DOM `node --test` suite; plain CSS.

**Spec:** `docs/superpowers/specs/2026-10-06-recipe-browser-design.md`

## Global Constraints

- Public repo: no real LAN IPs, tokens or house data in code, tests, docs or fixtures (placeholders such as `http://mealie` and `192.168.1.50` only). `tests/test_no_house_data.py` enforces it; run it before every push.
- `MEALIE_API_TOKEN` comes only from the environment (`integrations.mealie_token(env)`); it never reaches the browser or a log line.
- Every Mealie read fails soft (`{"available": False}`, never raises; the routes have no global handler). Every id/slug that goes into an upstream URL path is validated first. A reply of the wrong shape is "unavailable", never an empty library.
- Read-only feature: no writes to Mealie; no new env var, integration id or `/health/full` source (it rides `mealie` / the `meals` source; a failing recipe read must not turn the dinner tile red; only the shared `auth_rejected` flag is touched).
- Plain text only: the view never renders Mealie markdown or HTML (everything goes through `escapeHtml`; line breaks become `<br>`).
- Pi 3 budget: no `backdrop-filter`, no animation or transition, lazy thumbnails, at most 200 cards, nothing on a timer. CLAUDE.md iOS traps apply (nothing `position: fixed` with `backdrop-filter`, no transform on fixed interactive elements, tap targets >= 44 px on the phone).
- Every class used in markup must have a CSS rule (`test_every_referenced_class_is_styled`), including classes added with `classList.add`.
- Run Python tests with `PYTHONUTF8=1 PYTHONPATH=src <venv python> -m pytest ...` (a venv with `requirements.txt` + `pillow` + `pytest`; on the dev PC: `C:\Users\mrtim\AppData\Local\Temp\claude\C--Users-mrtim-Documents-family-hub-deploy\3616fd7c-405a-4982-8032-ad1bc192ee43\scratchpad\venv\Scripts\python.exe`). 50 Python tests fail identically on a clean `origin/main` on Windows (`test_api` 2, `test_backup` 30, `test_caldav` 2, `test_check_changelog` 1, `test_google_client` 2, `test_install_hooks` 13): not from this branch. JS: `node --test tests/js/*.mjs`.
- **Editing caution on the dev PC's shell tool:** a `python - <<'PY'` heredoc halves backslashes, which silently corrupts regexes (`\b` becomes a backspace character, `\r\n` becomes real CR/LF). Make edits containing backslashes with the Edit/Write tools, or build the pattern from `chr(92)`.
- Every commit touching `src/**` needs a NEW bullet (a line starting `- `) under `## [Unreleased]` in `CHANGELOG.md` (the hook counts new bullets, not edits). Use the existing `### Fixed`/`### Added` headings; do not create a second heading of the same name. Commit messages end with the two attribution lines the session was given.
- Work on branch `feat/recipe-browser` (created from `origin/main`).

## Review Focus

Failure modes the spec implies that no happy-path test exercises; each is pinned by a test in the task that owns the code:

1. **A recipe deleted or renamed in Mealie while the view is open:** tapping it gives a clean 404, a toast, and the grid stays (the view must not strand on a "Loading..." detail) (Task 2 `unknown slug`, Task 6 `a failed detail fetch`).
2. **Hostile or enormous text:** recipe names, categories, ingredients, steps and notes containing markup, markdown, or thousands of characters render inert and clipped; a library of 1000 entries is capped at 200 with a truncated note; entries with no usable slug or name are skipped (Task 1, Task 2, Task 6 XSS test).
3. **A changed Mealie reply shape:** no `items` list, a non-dict body, or a recipe body with no name reads as unavailable, never as "No recipes yet" (Task 1, Task 2).
4. **Typing, tapping and fetches racing:** typing in the search box never repaints the box (focus and the on-screen keyboard survive); a late older list or detail reply never overwrites a newer one; tapping a second card while the first loads shows the second (Task 6).
5. **Mealie down or the token rejected on open:** the grid shows "not reachable" / "needs a Mealie token" with a Try-again button; the previously opened state is not shown as if current; a thumbnail that fails to load becomes a placeholder, not a broken-image icon (Task 6).

---

## File Structure

- Modify `src/family_hub/meals.py`: recipe list + detail reads, image sizes and a thumbnail cache (one self-contained block before `fetch_image`, plus `fetch_image` itself).
- Modify `src/family_hub/app.py`: two routes and a `size` query on the image route.
- Modify `src/family_hub/demo.py`: `demo_recipes()`, `demo_recipe(slug)`.
- Modify `src/family_hub/web/static/common.js`: `RECIPE_SORTS`, `recipeFilter`, `recipeSort`, `recipeCategories`, and `idleReturnMs('recipes')`.
- Modify `src/family_hub/web/static/hub.js`: the `recipes` overlay (state, grid, controls, detail, fetchers, handlers); the Dinner header button; removal of the `meals-full` iframe branch.
- Modify `src/family_hub/web/static/styles.css`: the Recipes view styles and phone-shell rules.
- Modify tests: `tests/test_meals.py`, `tests/test_demo.py`, `tests/test_static.py`, `tests/js/hub.test.mjs`, `tests/js/hub-dom.test.mjs`.
- Modify docs: `CHANGELOG.md`, `README.md`, `docs/hub.png`.

---

### Task 1: Recipe list read (`meals.recipes_tile`)

**Files:**
- Modify: `src/family_hub/meals.py` (constants after `ITEM_TEXT_MAX`, caches after `_shop_gen`, `reset_caches`, a new block before `fetch_image`)
- Test: `tests/test_meals.py` (extend `FakeMealie`; new section)

**Interfaces:**
- Consumes: existing `valid_uuid`, `_headers`, `_auth_failed`, `_note_auth`, `_is_int`, `TIMEOUT`, `log`.
- Produces: `async def recipes_tile(client, cfg, env) -> dict` returning `{"available": False}` | `{"available": False, "needs_auth": True}` | `{"available": True, "truncated": bool, "total": int, "recipes": [{"slug", "id", "name", "time", "has_image", "categories", "tags", "added", "made", "rating"}]}`; helpers `_one_line(value, limit)`, `_paragraphs(value, limit)`, `_names(value)`, `_iso(value)`, `_recipe_summary(raw)`; constants `RECIPES_TTL`, `RECIPES_MAX`, `RECIPES_TIMEOUT`, `RECIPE_NAME_MAX`, `RECIPE_TIME_MAX`, `RECIPE_TEXT_MAX`, `RECIPE_DESC_MAX`, `RECIPE_LINE_MAX`, `RECIPE_MAX_ROWS`, `RECIPE_DETAIL_TTL`, `RECIPE_DETAIL_CACHE_MAX`, `_SLUG`; caches `_recipes_cache`, `_recipe_cache`.

- [ ] **Step 1: Extend the test fake** (`tests/test_meals.py`). Add a fixture helper after `item(...)`:

```python
def recipe(slug, name=None, rid=RID, **kw):
    """A recipe summary as Mealie's /api/recipes returns it."""
    r = {"id": rid, "slug": slug, "name": name or slug.replace("-", " ").title(), "image": "abc",
         "totalTime": "30 Minutes",
         "recipeCategory": [{"id": "c1", "name": "Dinner", "slug": "dinner"}],
         "tags": [{"id": "t1", "name": "Easy", "slug": "easy"}],
         "rating": 4, "dateAdded": "2026-09-01T10:00:00+00:00", "lastMade": None}
    r.update(kw)
    return r
```

Change `FakeMealie.__init__` to `def __init__(self, plan=None, lists=None, items=None, recipes=None, details=None):` and add `self.recipes = list(recipes or [])`, `self.details = dict(details or {})`, `self.missing_files = set()` (file names that 404). Add these branches in `handler` before the final `return httpx.Response(404)` (and replace the existing media branch so a missing file 404s):

```python
        if req.method == "GET" and p == "/api/recipes":
            per = int(req.url.params.get("perPage", 50))
            return httpx.Response(200, json={"page": 1, "per_page": per, "total": len(self.recipes),
                                             "total_pages": 1, "items": self.recipes[:per]})
        if req.method == "GET" and p.startswith("/api/recipes/"):
            found = self.details.get(p.rsplit("/", 1)[1])
            if found is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=found)
        if req.method == "GET" and p.startswith("/api/media/recipes/"):
            if p.rsplit("/", 1)[1] in self.missing_files:
                return httpx.Response(404)
            return httpx.Response(200, content=b"IMG", headers={"content-type": "image/webp"})
```
(The old media branch is the same minus the `missing_files` check.)

- [ ] **Step 2: Write the failing tests** (append a section `# ---- recipe list`):

```python
# ------------------------------------------------------------------ recipe list

def recipes(fake, cfg=None):
    return run(fake, lambda c, cfg_: meals.recipes_tile(c, cfg_, ENV), cfg)


def test_recipes_read_shape_and_the_single_request_it_makes():
    fake = FakeMealie(recipes=[
        recipe("baked-ziti", "Baked Ziti", lastMade="2026-09-20T18:00:00+00:00"),
        recipe("soup", "Soup", image=None, rating=0, totalTime=None)])
    out = recipes(fake)
    assert out["available"] is True and out["truncated"] is False and out["total"] == 2
    assert out["recipes"][0] == {
        "slug": "baked-ziti", "id": RID, "name": "Baked Ziti", "time": "30 Minutes", "has_image": True,
        "categories": ["Dinner"], "tags": ["Easy"], "added": "2026-09-01T10:00:00+00:00",
        "made": "2026-09-20T18:00:00+00:00", "rating": 4}
    soup = out["recipes"][1]
    assert soup["has_image"] is False and soup["time"] is None and soup["rating"] is None and soup["made"] is None
    reqs = [c for c in fake.calls if c["path"] == "/api/recipes"]
    assert len(reqs) == 1
    assert reqs[0]["params"] == {"perPage": str(meals.RECIPES_MAX), "page": "1",
                                 "orderBy": "name", "orderDirection": "asc"}


@pytest.mark.parametrize("bad", [
    {"slug": "Bad Slug", "name": "x"}, {"slug": "", "name": "x"}, {"slug": "ok", "name": "   "},
    {"slug": "../x", "name": "x"}, {"slug": 5, "name": "x"}, {"name": "no slug"}, "junk", None, 5])
def test_recipes_skip_entries_with_no_usable_slug_or_name(bad, caplog):
    fake = FakeMealie(recipes=[recipe("good", "Good"), bad])
    with caplog.at_level(logging.WARNING, logger="family_hub.meals"):
        out = recipes(fake)
    assert [r["slug"] for r in out["recipes"]] == ["good"]
    assert "skipped 1" in caplog.text


def test_recipes_trim_cap_and_dedupe_text():
    cats = [{"name": f"Cat {n}"} for n in range(20)] + [{"name": "Cat 1"}, {"name": "  "}, "x", None]
    fake = FakeMealie(recipes=[recipe("a", "  A \n  very   long " + "x" * 300, recipeCategory=cats,
                                      totalTime="  1  Hour \n 30 Minutes ")])
    r = recipes(fake)["recipes"][0]
    assert r["name"].startswith("A very long xxx") and len(r["name"]) == meals.RECIPE_NAME_MAX
    assert r["time"] == "1 Hour 30 Minutes"
    assert len(r["categories"]) == 12 and r["categories"].count("Cat 1") == 1


@pytest.mark.parametrize("rating,want", [(4, 4), (4.5, 4.5), (5, 5), (0, None), (6, None), (-1, None),
                                         ("5", None), (True, None), (None, None)])
def test_recipes_rating_is_a_number_from_one_to_five_or_none(rating, want):
    assert recipes(FakeMealie(recipes=[recipe("a", rating=rating)]))["recipes"][0]["rating"] == want


def test_recipes_dates_must_look_like_iso_dates():
    r = recipes(FakeMealie(recipes=[recipe("a", dateAdded="yesterday", lastMade="2026-10-01")]))["recipes"][0]
    assert r["added"] is None and r["made"] == "2026-10-01"


def test_recipes_has_image_needs_a_photo_and_a_valid_id():
    out = recipes(FakeMealie(recipes=[recipe("a", image=""), recipe("b", rid="nope"), recipe("c")]))["recipes"]
    assert [r["has_image"] for r in out] == [False, False, True] and out[1]["id"] is None


def test_recipes_are_capped_but_the_true_total_and_truncated_flag_say_so():
    many = [recipe(f"r-{n}", f"R {n}") for n in range(meals.RECIPES_MAX + 30)]
    fake = FakeMealie(recipes=many)
    out = recipes(fake)
    assert len(out["recipes"]) == meals.RECIPES_MAX
    assert out["truncated"] is True and out["total"] == meals.RECIPES_MAX + 30


@pytest.mark.parametrize("body", [[], "x", 5, {}, {"items": "x"}, {"items": None}])
def test_recipes_with_no_items_list_are_unavailable_never_an_empty_library(body):
    fake = FakeMealie()
    inner = fake.handler
    def handler(req):
        if req.url.path == "/api/recipes":
            return httpx.Response(200, json=body)
        return inner(req)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.recipes_tile(c, mcfg(), ENV)
    assert asyncio.run(go()) == {"available": False, "needs_auth": False}
    assert meals._recipes_cache == {}


def test_recipes_items_that_are_all_junk_read_as_an_empty_library():
    out = recipes(FakeMealie(recipes=[None, 5, "x"]))
    assert out["available"] is True and out["recipes"] == []


def test_recipes_unconfigured_or_tokenless_make_no_request():
    fake = FakeMealie(recipes=[recipe("a")])
    assert run(fake, lambda c, cfg: meals.recipes_tile(c, cfg, ENV), Config()) == {"available": False}
    assert run(fake, lambda c, cfg: meals.recipes_tile(c, cfg, {})) == {"available": False, "needs_auth": True}
    assert fake.calls == []


@pytest.mark.parametrize("status,auth", [(401, True), (403, True), (500, False), (404, False)])
def test_recipes_upstream_errors_are_unavailable_and_flag_auth_only_for_401_403(status, auth):
    fake = FakeMealie(recipes=[recipe("a")])
    fake.fail[("GET", "/api/recipes")] = status
    assert recipes(fake) == {"available": False, "needs_auth": auth}
    assert meals._recipes_cache == {}


def test_recipes_transport_error_is_unavailable_and_never_cached():
    def handler(req):
        raise httpx.ConnectError("down")
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.recipes_tile(c, mcfg(), ENV)
    assert asyncio.run(go()) == {"available": False, "needs_auth": False}
    assert meals._recipes_cache == {}


def test_recipes_are_cached_briefly_and_expire(monkeypatch):
    fake = FakeMealie(recipes=[recipe("a")])
    clock = [1000.0]
    monkeypatch.setattr(meals.time, "monotonic", lambda: clock[0])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.recipes_tile(c, mcfg(), ENV)
            await meals.recipes_tile(c, mcfg(), ENV)                 # cached
            n1 = len(fake.log)
            clock[0] += meals.RECIPES_TTL + 1
            await meals.recipes_tile(c, mcfg(), ENV)                 # expired
            return n1, len(fake.log)
    assert asyncio.run(go()) == (1, 2)


def test_recipes_do_not_touch_the_dinner_source_state():
    recipes(FakeMealie(recipes=[recipe("a")]))
    assert "last_ok" not in tiles.SOURCE_STATE.get("meals", {})
```

- [ ] **Step 3: Run to verify they fail**

Run: `PYTHONUTF8=1 PYTHONPATH=src <venv python> -m pytest tests/test_meals.py -q -k recipes`
Expected: FAIL with `AttributeError: module 'family_hub.meals' has no attribute 'recipes_tile'`.

- [ ] **Step 4: Implement.** In `meals.py` add the constants after `ITEM_TEXT_MAX`:

```python
RECIPES_TTL = 300.0             # the library changes when someone edits Mealie; the view re-reads on open
RECIPES_MAX = 200
RECIPES_TIMEOUT = 8.0           # up to 200 summaries come back in one reply
RECIPE_DETAIL_TTL = 300.0
RECIPE_DETAIL_CACHE_MAX = 32
RECIPE_NAME_MAX = 120
RECIPE_TIME_MAX = 40
RECIPE_LINE_MAX = 300           # one ingredient
RECIPE_DESC_MAX = 600
RECIPE_TEXT_MAX = 2000          # one step or note
RECIPE_MAX_ROWS = 200           # ingredients / steps / notes per recipe
_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,199}")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
```

After `_shop_gen = 0` add the caches, and clear them in `reset_caches`:

```python
# Mealie base -> (expiry monotonic, result); (base, slug) -> (expiry, result), bounded.
_recipes_cache: dict[str, tuple[float, dict]] = {}
_recipe_cache: dict[tuple[str, str], tuple[float, dict]] = {}
```
```python
def reset_caches() -> None:
    _cache.clear()
    _image_cache.clear()
    _shop_cache.clear()
    _recipes_cache.clear()
    _recipe_cache.clear()
```

Add before `async def fetch_image`:

```python
def _one_line(value: object, limit: int) -> str:
    """One line of plain text: whitespace collapsed, clipped; anything that is not text is ''."""
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _paragraphs(value: object, limit: int) -> str:
    """Plain text that keeps its line breaks (a step, a note): each line trimmed, runs of
    blank lines collapsed, clipped. Never markdown or HTML: the page escapes it."""
    if not isinstance(value, str):
        return ""
    text = "\n".join(" ".join(line.split()) for line in value.splitlines()).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit]


def _names(value: object) -> list[str]:
    """The names in a list of {name} dicts (categories, tags): trimmed, de-duplicated, at most 12."""
    out: list[str] = []
    for v in value if isinstance(value, list) else []:
        n = _one_line(v.get("name"), RECIPE_NAME_MAX) if isinstance(v, dict) else ""
        if n and n not in out:
            out.append(n)
    return out[:12]


def _iso(value: object) -> str | None:
    return value[:32] if isinstance(value, str) and _ISO.match(value) else None


def _recipe_summary(raw: object) -> dict | None:
    """One recipe as the grid shows it, or None when it has no usable slug or name."""
    if not isinstance(raw, dict):
        return None
    slug = raw.get("slug")
    name = _one_line(raw.get("name"), RECIPE_NAME_MAX)
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug) or not name:
        return None
    rid = raw.get("id") if valid_uuid(raw.get("id")) else None
    rating = raw.get("rating")
    ok_rating = isinstance(rating, (int, float)) and not isinstance(rating, bool) and 0 < rating <= 5
    return {"slug": slug, "id": rid, "name": name,
            "time": _one_line(raw.get("totalTime"), RECIPE_TIME_MAX) or None,
            "has_image": bool(rid and isinstance(raw.get("image"), str) and raw["image"]),
            "categories": _names(raw.get("recipeCategory")), "tags": _names(raw.get("tags")),
            "added": _iso(raw.get("dateAdded")), "made": _iso(raw.get("lastMade")),
            "rating": rating if ok_rating else None}


async def recipes_tile(client, cfg, env: dict) -> dict:
    """``{available, needs_auth?, truncated, total, recipes: [...]}``: every recipe's summary in
    one request (capped at RECIPES_MAX; ``truncated`` says so), for the Recipes view to filter
    and sort on the screen. Never raises; errors are never cached. A reply with no ``items`` list
    is unavailable, never an empty library."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"available": False}
    if not mealie_token(env):
        return {"available": False, "needs_auth": True}
    hit = _recipes_cache.get(mc["base"])
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    try:
        r = await client.get(
            f"{mc['base']}/api/recipes",
            params={"perPage": RECIPES_MAX, "page": 1, "orderBy": "name", "orderDirection": "asc"},
            headers=_headers(env), timeout=RECIPES_TIMEOUT)
        r.raise_for_status()
        body = r.json()
    except json.JSONDecodeError as e:
        log.warning("meals recipes: non-JSON reply: %s", e)
        return {"available": False, "needs_auth": False}
    except (httpx.HTTPError, ValueError) as e:
        log.warning("meals recipes unavailable: %s", e)
        _note_auth(e)
        return {"available": False, "needs_auth": _auth_failed(e)}
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        log.warning("meals recipes: the reply carries no items list")
        return {"available": False, "needs_auth": False}
    shaped = [s for s in (_recipe_summary(x) for x in items[:RECIPES_MAX]) if s is not None]
    if len(shaped) != len(items[:RECIPES_MAX]):
        log.warning("meals recipes: skipped %d entries with no usable slug or name",
                    len(items[:RECIPES_MAX]) - len(shaped))
    total = body.get("total") if _is_int(body.get("total")) else len(items)
    result = {"available": True, "truncated": total > len(items), "total": total, "recipes": shaped}
    _recipes_cache[mc["base"]] = (time.monotonic() + RECIPES_TTL, result)
    return result
```

- [ ] **Step 5: Run to verify they pass, then the whole file**

Run: `PYTHONUTF8=1 PYTHONPATH=src <venv python> -m pytest tests/test_meals.py -q`
Expected: all pass (the pre-existing meals and shopping tests included).

- [ ] **Step 6: Changelog bullet and commit**

Add under `## [Unreleased]` / `### Added` in `CHANGELOG.md`:

```markdown
- Recipes: the hub can read the Mealie recipe library for a native Recipes view
  (`GET /api/mealie/recipes`): every recipe's name, photo flag, time, categories, tags and
  dates in one cached request, capped at 200, read-only and fail-soft.
```
```bash
git add CHANGELOG.md src/family_hub/meals.py tests/test_meals.py
git commit -m "feat(meals): fail-soft Mealie recipe list read for the Recipes view"
```

---

### Task 2: Recipe detail read (`meals.recipe_detail`)

**Files:**
- Modify: `src/family_hub/meals.py` (after `recipes_tile`)
- Test: `tests/test_meals.py`

**Interfaces:**
- Consumes: Task 1's helpers/constants/caches, `_SLUG`, `_headers`, `TIMEOUT`.
- Produces: `async def recipe_detail(client, cfg, env, slug) -> dict`: `{"available": True, "recipe": {"slug", "id", "name", "has_image", "servings", "prep", "cook", "total", "description", "ingredients": [{"text"} | {"heading"}], "steps": [{"title", "text"}], "notes": [{"title", "text"}]}}` or `{"available": False, ...}` with optional `status` (422 bad slug, 404 unknown) and `error`.

- [ ] **Step 1: Write the failing tests**

```python
# ---------------------------------------------------------------- recipe detail

def detail_body(slug="baked-ziti", **kw):
    b = {"id": RID, "slug": slug, "name": "Baked Ziti", "image": "abc", "recipeServings": 6,
         "prepTime": "15 Minutes", "cookTime": "45 Minutes", "totalTime": "1 Hour",
         "description": "Cheesy pasta.",
         "recipeIngredient": [{"display": "1 pound ziti", "note": "", "title": None},
                              {"display": "", "note": "salt to taste", "title": None}],
         "recipeInstructions": [{"title": "", "summary": "", "text": "Boil the pasta.\n\nDrain."}],
         "notes": [{"title": "Tip", "text": "Use fresh basil."}]}
    b.update(kw)
    return b


def detail(fake, slug="baked-ziti", cfg=None, env=ENV):
    return run(fake, lambda c, cfg_: meals.recipe_detail(c, cfg_, env, slug), cfg)


def test_detail_shape():
    out = detail(FakeMealie(details={"baked-ziti": detail_body()}))
    assert out == {"available": True, "recipe": {
        "slug": "baked-ziti", "id": RID, "name": "Baked Ziti", "has_image": True, "servings": 6,
        "prep": "15 Minutes", "cook": "45 Minutes", "total": "1 Hour", "description": "Cheesy pasta.",
        "ingredients": [{"text": "1 pound ziti"}, {"text": "salt to taste"}],
        "steps": [{"title": None, "text": "Boil the pasta.\n\nDrain."}],
        "notes": [{"title": "Tip", "text": "Use fresh basil."}]}}


def test_detail_section_titles_become_headings_and_blank_rows_are_dropped():
    body = detail_body(recipeIngredient=[
        {"title": "For the sauce", "display": "1 can tomatoes"}, {"display": "  ", "note": "", "originalText": ""},
        {"title": "Topping", "display": ""}, "junk", None],
        recipeInstructions=[{"title": "Prep", "text": ""}, {"text": "  "}, {"summary": "Bake it."}],
        notes=[{"title": "", "text": ""}])
    r = detail(FakeMealie(details={"baked-ziti": body}))["recipe"]
    assert r["ingredients"] == [{"heading": "For the sauce"}, {"text": "1 can tomatoes"}, {"heading": "Topping"}]
    assert r["steps"] == [{"title": "Prep", "text": ""}, {"title": None, "text": "Bake it."}]
    assert r["notes"] == []


def test_detail_markup_and_markdown_stay_inert_literal_text():
    body = detail_body(name="<b>Zesty</b> **Ziti**", description="<script>alert(1)</script>",
                       recipeInstructions=[{"text": "# Heading\n<img src=x onerror=1>"}])
    r = detail(FakeMealie(details={"baked-ziti": body}))["recipe"]
    assert r["name"] == "<b>Zesty</b> **Ziti**" and r["description"] == "<script>alert(1)</script>"
    assert r["steps"][0]["text"] == "# Heading\n<img src=x onerror=1>"


def test_detail_clips_and_caps_everything():
    big = detail_body(name="n" * 500, description="d" * 5000,
                      recipeIngredient=[{"display": "i" * 900}] * 500,
                      recipeInstructions=[{"text": "s" * 9000}] * 500, notes=[{"text": "t" * 9000}] * 500)
    r = detail(FakeMealie(details={"baked-ziti": big}))["recipe"]
    assert len(r["name"]) == meals.RECIPE_NAME_MAX and len(r["description"]) == meals.RECIPE_DESC_MAX
    assert len(r["ingredients"]) == len(r["steps"]) == len(r["notes"]) == meals.RECIPE_MAX_ROWS
    assert len(r["ingredients"][0]["text"]) == meals.RECIPE_LINE_MAX
    assert len(r["steps"][0]["text"]) == len(r["notes"][0]["text"]) == meals.RECIPE_TEXT_MAX


@pytest.mark.parametrize("servings,want", [(6, 6), (6.0, 6), (2.5, 2.5), (0, None), (-1, None), ("6", None), (True, None), (None, None)])
def test_detail_servings(servings, want):
    r = detail(FakeMealie(details={"baked-ziti": detail_body(recipeServings=servings)}))["recipe"]
    assert r["servings"] == want


@pytest.mark.parametrize("slug", ["", "Bad Slug", "../x", "a/b", "A", "x" * 201, None, 5, "ok\n"])
def test_detail_bad_slug_is_a_422_before_any_request(slug):
    fake = FakeMealie(details={"baked-ziti": detail_body()})
    out = detail(fake, slug=slug)
    assert out["available"] is False and out["status"] == 422
    assert fake.calls == []


def test_detail_unknown_slug_is_a_404():
    out = detail(FakeMealie(), slug="gone-recipe")
    assert out == {"available": False, "status": 404, "error": "no such recipe"}


@pytest.mark.parametrize("body", [[], "x", 5, {}, {"name": "  "}, {"slug": "x"}])
def test_detail_with_an_unusable_body_is_unavailable(body):
    fake = FakeMealie(details={"baked-ziti": body})
    assert detail(fake) == {"available": False, "needs_auth": False}


def test_detail_unconfigured_or_tokenless_make_no_request():
    fake = FakeMealie(details={"baked-ziti": detail_body()})
    assert detail(fake, cfg=Config()) == {"available": False}
    assert detail(fake, env={}) == {"available": False, "needs_auth": True}
    assert fake.calls == []


@pytest.mark.parametrize("status,auth", [(401, True), (403, True), (500, False)])
def test_detail_upstream_errors(status, auth):
    fake = FakeMealie(details={"baked-ziti": detail_body()})
    fake.fail[("GET", "/api/recipes/")] = status
    assert detail(fake) == {"available": False, "needs_auth": auth}
    assert meals._recipe_cache == {}


def test_detail_is_cached_per_slug_and_the_cache_is_bounded():
    fake = FakeMealie(details={f"r-{n}": detail_body(slug=f"r-{n}") for n in range(meals.RECIPE_DETAIL_CACHE_MAX + 5)})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.recipe_detail(c, mcfg(), ENV, "r-0")
            await meals.recipe_detail(c, mcfg(), ENV, "r-0")                 # cached
            n = len([1 for m, p in fake.log if p == "/api/recipes/r-0"])
            for k in range(meals.RECIPE_DETAIL_CACHE_MAX + 5):
                await meals.recipe_detail(c, mcfg(), ENV, f"r-{k}")
            return n
    assert asyncio.run(go()) == 1
    assert len(meals._recipe_cache) <= meals.RECIPE_DETAIL_CACHE_MAX
```

- [ ] **Step 2: Run to verify they fail**

Run: `... -m pytest tests/test_meals.py -q -k detail`
Expected: FAIL with `AttributeError: ... no attribute 'recipe_detail'`.

- [ ] **Step 3: Implement** (in `meals.py`, right after `recipes_tile`):

```python
def _rows(value: object) -> list:
    return value[:RECIPE_MAX_ROWS] if isinstance(value, list) else []


def _recipe_body(body: dict) -> dict | None:
    """One recipe as the detail view shows it, or None when it has no name."""
    name = _one_line(body.get("name"), RECIPE_NAME_MAX)
    if not name:
        return None
    rid = body.get("id") if valid_uuid(body.get("id")) else None
    ingredients: list[dict] = []
    for it in _rows(body.get("recipeIngredient")):
        if not isinstance(it, dict):
            continue
        heading = _one_line(it.get("title"), RECIPE_NAME_MAX)
        text = next((t for t in (_one_line(it.get(k), RECIPE_LINE_MAX)
                                 for k in ("display", "note", "originalText")) if t), "")
        if heading:
            ingredients.append({"heading": heading})
        if text:
            ingredients.append({"text": text})
    steps = []
    for st in _rows(body.get("recipeInstructions")):
        if not isinstance(st, dict):
            continue
        text = _paragraphs(st.get("text"), RECIPE_TEXT_MAX) or _paragraphs(st.get("summary"), RECIPE_TEXT_MAX)
        title = _one_line(st.get("title"), RECIPE_NAME_MAX) or None
        if text or title:
            steps.append({"title": title, "text": text})
    notes = []
    for n in _rows(body.get("notes")):
        if not isinstance(n, dict):
            continue
        text = _paragraphs(n.get("text"), RECIPE_TEXT_MAX)
        title = _one_line(n.get("title"), RECIPE_NAME_MAX) or None
        if text:
            notes.append({"title": title, "text": text})
    sv = body.get("recipeServings")
    servings = None
    if isinstance(sv, (int, float)) and not isinstance(sv, bool) and sv > 0:
        servings = int(sv) if float(sv).is_integer() else sv
    return {"slug": body.get("slug") if isinstance(body.get("slug"), str) else None, "id": rid, "name": name,
            "has_image": bool(rid and isinstance(body.get("image"), str) and body["image"]),
            "servings": servings,
            "prep": _one_line(body.get("prepTime"), RECIPE_TIME_MAX) or None,
            "cook": _one_line(body.get("cookTime"), RECIPE_TIME_MAX) or None,
            "total": _one_line(body.get("totalTime"), RECIPE_TIME_MAX) or None,
            "description": _one_line(body.get("description"), RECIPE_DESC_MAX),
            "ingredients": ingredients, "steps": steps, "notes": notes}


async def recipe_detail(client, cfg, env: dict, slug: object) -> dict:
    """One recipe's detail. ``{available, recipe}``, or ``{available: False, status?, error?}``:
    422 for a slug that cannot be one (no request made), 404 for a recipe Mealie does not have.
    Never raises; errors are never cached."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"available": False}
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        return {"available": False, "status": 422, "error": "not a recipe slug"}
    if not mealie_token(env):
        return {"available": False, "needs_auth": True}
    key = (mc["base"], slug)
    hit = _recipe_cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    try:
        r = await client.get(f"{mc['base']}/api/recipes/{slug}", headers=_headers(env), timeout=TIMEOUT)
        if r.status_code == 404:
            return {"available": False, "status": 404, "error": "no such recipe"}
        r.raise_for_status()
        body = r.json()
    except json.JSONDecodeError as e:
        log.warning("meals recipe %s: non-JSON reply: %s", slug, e)
        return {"available": False, "needs_auth": False}
    except (httpx.HTTPError, ValueError) as e:
        log.warning("meals recipe %s unavailable: %s", slug, e)
        _note_auth(e)
        return {"available": False, "needs_auth": _auth_failed(e)}
    shaped = _recipe_body(body) if isinstance(body, dict) else None
    if shaped is None:
        log.warning("meals recipe %s: the reply has no usable recipe", slug)
        return {"available": False, "needs_auth": False}
    shaped["slug"] = slug
    result = {"available": True, "recipe": shaped}
    if len(_recipe_cache) >= RECIPE_DETAIL_CACHE_MAX:
        _recipe_cache.pop(next(iter(_recipe_cache)))
    _recipe_cache[key] = (time.monotonic() + RECIPE_DETAIL_TTL, result)
    return result
```

- [ ] **Step 4: Run to verify they pass, then the whole file**

Run: `... -m pytest tests/test_meals.py -q`
Expected: all pass.

- [ ] **Step 5: Changelog bullet and commit**

```markdown
- Recipes: `GET /api/mealie/recipes/{slug}` returns one recipe's photo flag, times, servings,
  description, ingredients (with section headings), steps and notes as plain trimmed text.
```
```bash
git add CHANGELOG.md src/family_hub/meals.py tests/test_meals.py
git commit -m "feat(meals): fail-soft Mealie recipe detail read"
```

---

### Task 3: Photo sizes and a bigger thumbnail cache

**Files:**
- Modify: `src/family_hub/meals.py` (`fetch_image`, constants, `reset_caches`)
- Test: `tests/test_meals.py`

**Interfaces:**
- Consumes: existing `_image_cache`, `IMAGE_CACHE_MAX`, `IMAGE_TTL`, `IMAGE_TYPES`, `IMAGE_MAX_BYTES`.
- Produces: `fetch_image(client, cfg, env, recipe_id, size="min")` where `size` is `"min"` (today's behaviour, cache `_image_cache`, 16 entries) or `"tiny"` (tries `tiny-original.webp` then falls back to `min-original.webp`; cache `_thumb_cache`, `THUMB_CACHE_MAX = 160`); any other size returns `None`. Constants `IMAGE_FILES`, `THUMB_CACHE_MAX`.

- [ ] **Step 1: Write the failing tests**

```python
# ----------------------------------------------------------------- photo sizes

def photo(fake, size, rid=RID, cfg=None):
    return run(fake, lambda c, cfg_: meals.fetch_image(c, cfg_, ENV, rid, size), cfg)


def test_the_default_photo_size_is_still_the_medium_one():
    fake = FakeMealie()
    got = run(fake, lambda c, cfg: meals.fetch_image(c, cfg, ENV, RID))
    assert got == (b"IMG", "image/webp")
    assert fake.log[-1] == ("GET", f"/api/media/recipes/{RID}/images/min-original.webp")


def test_tiny_asks_for_the_tiny_file_and_caches_it_apart_from_the_medium_one():
    fake = FakeMealie()
    assert photo(fake, "tiny") == (b"IMG", "image/webp")
    assert fake.log[-1] == ("GET", f"/api/media/recipes/{RID}/images/tiny-original.webp")
    n = len(fake.log)
    assert photo(fake, "tiny") == (b"IMG", "image/webp") and len(fake.log) == n, "second call is cached"
    assert RID in meals._thumb_cache and RID not in meals._image_cache


def test_tiny_falls_back_to_the_medium_file_when_the_recipe_has_no_tiny_one():
    fake = FakeMealie()
    fake.missing_files = {"tiny-original.webp"}
    assert photo(fake, "tiny") == (b"IMG", "image/webp")
    assert [p.rsplit("/", 1)[1] for m, p in fake.log if "/images/" in p] == ["tiny-original.webp", "min-original.webp"]


def test_tiny_with_neither_file_is_none_and_never_cached():
    fake = FakeMealie()
    fake.missing_files = {"tiny-original.webp", "min-original.webp"}
    assert photo(fake, "tiny") is None and meals._thumb_cache == {}


@pytest.mark.parametrize("size", ["huge", "", "TINY", None, "../x", "original"])
def test_an_unknown_photo_size_is_none_with_no_request(size):
    fake = FakeMealie()
    assert photo(fake, size) is None and fake.calls == []


def test_the_thumbnail_cache_holds_a_whole_library_but_is_still_bounded():
    fake = FakeMealie()
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            for n in range(meals.THUMB_CACHE_MAX + 10):
                await meals.fetch_image(c, mcfg(), ENV, f"{n:08d}-0000-4000-8000-000000000000", "tiny")   # a real UUID shape: f"{n:036d}" is not one and would cache nothing
    asyncio.run(go())
    assert meals.IMAGE_CACHE_MAX < len(meals._thumb_cache) <= meals.THUMB_CACHE_MAX
```

- [ ] **Step 2: Run to verify they fail**

Run: `... -m pytest tests/test_meals.py -q -k "photo_size or tiny or thumbnail"`
Expected: FAIL (`fetch_image() takes 4 positional arguments but 5 were given`, `no attribute '_thumb_cache'`).

- [ ] **Step 3: Implement.** Add near the other image constants:

```python
IMAGE_FILES = {"min": ("min-original.webp",), "tiny": ("tiny-original.webp", "min-original.webp")}
THUMB_CACHE_MAX = 160           # a grid of thumbnails: the whole library, about 90 KB each
```
Add `_thumb_cache: dict[str, tuple[float, bytes, str]] = {}` beside `_image_cache` and `_thumb_cache.clear()` in `reset_caches`. Replace `fetch_image` with:

```python
async def fetch_image(client, cfg, env: dict, recipe_id: object, size: object = "min") -> tuple[bytes, str] | None:
    """A recipe photo as (bytes, content type), or None. ``size`` is "min" (the detail view,
    and the Dinner card) or "tiny" (the grid's thumbnails; falls back to "min" for a recipe with
    no tiny file). Cached for an hour, the thumbnails in their own larger cache."""
    mc = getattr(cfg, "mealie", None)
    if not mc or not valid_uuid(recipe_id) or size not in IMAGE_FILES:
        return None
    cache, cap = (_thumb_cache, THUMB_CACHE_MAX) if size == "tiny" else (_image_cache, IMAGE_CACHE_MAX)
    hit = cache.get(recipe_id)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1], hit[2]
    for file_name in IMAGE_FILES[size]:
        try:
            r = await client.get(
                f"{mc['base']}/api/media/recipes/{recipe_id}/images/{file_name}",
                headers=_headers(env) if mealie_token(env) else {}, timeout=TIMEOUT)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("meals image %s (%s) unavailable: %s", recipe_id, file_name, e)
            continue
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype not in IMAGE_TYPES or len(r.content) > IMAGE_MAX_BYTES:
            return None
        if len(cache) >= cap:
            cache.pop(next(iter(cache)))
        cache[recipe_id] = (time.monotonic() + IMAGE_TTL, r.content, ctype)
        return r.content, ctype
    return None
```

- [ ] **Step 4: Run to verify they pass, then the whole file**

Run: `... -m pytest tests/test_meals.py -q`
Expected: all pass (including `test_image_proxy_returns_bytes_caches_and_rejects_non_images_and_bad_ids` and `test_image_cache_is_bounded`, unchanged).

- [ ] **Step 5: Changelog bullet and commit**

```markdown
- Recipes: the photo proxy takes `?size=tiny` (the grid's thumbnails, with their own cache big
  enough for a whole library) next to the existing medium size.
```
```bash
git add CHANGELOG.md src/family_hub/meals.py tests/test_meals.py
git commit -m "feat(meals): tiny recipe thumbnails with their own cache"
```

---

### Task 4: Routes, demo data

**Files:**
- Modify: `src/family_hub/app.py` (next to `mealie_image`, ~line 3081)
- Modify: `src/family_hub/demo.py` (after `demo_shopping`)
- Test: `tests/test_meals.py` (routes), `tests/test_demo.py`

**Interfaces:**
- Consumes: Tasks 1-3 functions; `DEMO`, `fdemo`, `_http`, `cfg`, `HTTPException`, `Response`.
- Produces: `GET /api/mealie/recipes`, `GET /api/mealie/recipes/{slug}` (422/404 as `HTTPException`), `GET /api/mealie/image/{recipe_id}?size=tiny|min` (422 for any other size); `demo.demo_recipes() -> dict` (same shape as `recipes_tile`), `demo.demo_recipe(slug) -> dict | None` (same shape as `recipe_detail`'s success).

- [ ] **Step 1: Write the failing tests.** Routes (`tests/test_meals.py`, uses the `app_env` fixture):

```python
# ----------------------------------------------------------------- recipe routes

def test_route_recipes_list_and_detail_round_trip(app_env):
    appmod, c, fake = app_env
    fake.recipes.append(recipe("baked-ziti", "Baked Ziti"))
    fake.details["baked-ziti"] = detail_body()
    got = c.get("/api/mealie/recipes").json()
    assert got["available"] is True and [r["slug"] for r in got["recipes"]] == ["baked-ziti"]
    one = c.get("/api/mealie/recipes/baked-ziti").json()
    assert one["available"] is True and one["recipe"]["name"] == "Baked Ziti"


def test_route_recipe_detail_statuses(app_env):
    appmod, c, fake = app_env
    assert c.get("/api/mealie/recipes/gone-recipe").status_code == 404
    assert c.get("/api/mealie/recipes/Bad%20Slug").status_code == 422
    assert c.get("/api/mealie/recipes/..%2F..%2Fx").status_code in (404, 405, 422)
    assert not [x for x in fake.calls if "/api/recipes/" in x["path"] and "gone" not in x["path"]]
    fake.details["a-recipe"] = detail_body(slug="a-recipe")
    fake.fail[("GET", "/api/recipes/")] = 500
    assert c.get("/api/mealie/recipes/a-recipe").json() == {"available": False, "needs_auth": False}


def test_route_recipes_unavailable_is_a_200_with_a_reason_flag(app_env):
    appmod, c, fake = app_env
    fake.fail[("GET", "/api/recipes")] = 401
    assert c.get("/api/mealie/recipes").json() == {"available": False, "needs_auth": True}


def test_route_image_size_option(app_env):
    appmod, c, fake = app_env
    assert c.get(f"/api/mealie/image/{RID}?size=tiny").status_code == 200
    assert fake.log[-1][1].endswith("/tiny-original.webp")
    assert c.get(f"/api/mealie/image/{RID}").status_code == 200
    assert fake.log[-1][1].endswith("/min-original.webp")
    assert c.get(f"/api/mealie/image/{RID}?size=huge").status_code == 422
```

Demo (`tests/test_demo.py`, after the shopping demo tests):

```python
def test_demo_recipes_library_shows_every_state(demo_client):
    t = demo_client.get("/api/mealie/recipes").json()
    assert t["available"] is True and t["truncated"] is False and t["total"] == len(t["recipes"]) >= 10
    rs = t["recipes"]
    assert [r["name"] for r in rs] == sorted((r["name"] for r in rs), key=str.casefold), "A to Z"
    assert len({c for r in rs for c in r["categories"]}) >= 4, "enough categories for the chips"
    assert any(r["made"] for r in rs) and any(not r["made"] for r in rs)
    assert any(r["rating"] for r in rs) and any(not r["rating"] for r in rs)
    assert all(set(r) == {"slug", "id", "name", "time", "has_image", "categories", "tags", "added", "made", "rating"} for r in rs)


def test_demo_recipe_detail_and_unknown_slug(demo_client):
    slug = demo_client.get("/api/mealie/recipes").json()["recipes"][0]["slug"]
    d = demo_client.get(f"/api/mealie/recipes/{slug}").json()
    assert d["available"] is True and d["recipe"]["ingredients"] and d["recipe"]["steps"]
    assert any("heading" in i for i in d["recipe"]["ingredients"]), "a section heading shows"
    assert d["recipe"]["notes"]
    assert demo_client.get("/api/mealie/recipes/not-in-the-demo").status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `... -m pytest tests/test_meals.py tests/test_demo.py -q -k "recipe"`
Expected: FAIL (404 for the new routes; `demo_recipes` missing).

- [ ] **Step 3: Implement the routes** (`app.py`, replace `mealie_image` and add the two routes right after it):

```python
@app.get("/api/mealie/image/{recipe_id}")
async def mealie_image(recipe_id: str, size: str = "min"):
    if size not in ("min", "tiny"):
        raise HTTPException(422, "size must be min or tiny")
    got = None if DEMO else await meals.fetch_image(_http, cfg, os.environ, recipe_id, size)
    if got is None:
        raise HTTPException(404, "no photo")
    body, ctype = got
    return Response(body, media_type=ctype, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/mealie/recipes")
async def mealie_recipes():
    if DEMO:
        return fdemo.demo_recipes()      # canned library; no Mealie hit
    return await meals.recipes_tile(_http, cfg, os.environ)


@app.get("/api/mealie/recipes/{slug}")
async def mealie_recipe(slug: str):
    if DEMO:
        got = fdemo.demo_recipe(slug)
        if got is None:
            raise HTTPException(404, "no such recipe")
        return got
    res = await meals.recipe_detail(_http, cfg, os.environ, slug)
    if res.get("status"):
        raise HTTPException(res["status"], res.get("error") or "recipe request failed")
    return res
```

- [ ] **Step 4: Implement the demo data** (`demo.py`, after `demo_shopping`):

```python
# (slug, name, time, categories, tags, days since added, days since made or None, rating or None)
_DEMO_RECIPES = [
    ("baked-ziti", "Baked Ziti", "1 Hour", ["Dinner", "Pasta"], ["Family favourite"], 120, 6, 5),
    ("banana-bread", "Banana Bread", "1 Hour 10 Minutes", ["Dessert", "Breakfast"], ["Baking"], 200, 40, 4),
    ("blueberry-pancakes", "Blueberry Pancakes", "25 Minutes", ["Breakfast"], ["Weekend"], 90, 20, 4),
    ("chicken-tortilla-soup", "Chicken Tortilla Soup", "45 Minutes", ["Dinner", "Soup"], ["Freezer friendly"], 60, 12, 4),
    ("chocolate-chip-cookies", "Chocolate Chip Cookies", "30 Minutes", ["Dessert"], ["Baking", "Kids"], 300, 70, 5),
    ("crock-pot-chicken-dumplings", "Crock Pot Chicken & Dumplings", "6 Hours", ["Dinner"], ["Slow cooker"], 30, 2, 5),
    ("homemade-pizza-night", "Homemade Pizza Night", "1 Hour 15 Minutes", ["Dinner"], ["Kids", "Weekend"], 150, 9, 4),
    ("lemon-herb-salmon", "Lemon Herb Salmon", "25 Minutes", ["Dinner", "Seafood"], ["Quick"], 45, 3, 4),
    ("overnight-oats", "Overnight Oats", "5 Minutes", ["Breakfast"], ["Quick"], 5, None, None),
    ("sheet-pan-sausage-veggies", "Sheet Pan Sausage & Veggies", "35 Minutes", ["Dinner"], ["Quick", "One pan"], 75, 1, 3),
    ("taco-tuesday-beef-tacos", "Taco Tuesday Beef Tacos", "30 Minutes", ["Dinner"], ["Kids"], 100, 15, 4),
    ("veggie-stir-fry", "Veggie Stir Fry", "20 Minutes", ["Dinner", "Vegetarian"], ["Quick"], 10, None, None),
]


def demo_recipes() -> dict:
    """A live-shaped recipe library (matches meals.recipes_tile): twelve recipes across several
    categories, A to Z, some never made or unrated so every sort shows its ordering. No photos
    (the demo has no Mealie to serve them), so every card shows its placeholder."""
    import datetime as _dt
    today = _dt.date.today()
    day = lambda n: None if n is None else (today - _dt.timedelta(days=n)).isoformat() + "T12:00:00+00:00"   # noqa: E731
    recipes = [{"slug": s, "id": None, "name": n, "time": t, "has_image": False, "categories": list(c),
                "tags": list(g), "added": day(a), "made": day(m), "rating": r}
               for s, n, t, c, g, a, m, r in _DEMO_RECIPES]
    return {"available": True, "truncated": False, "total": len(recipes), "recipes": recipes}


def demo_recipe(slug) -> dict | None:
    """A canned recipe detail for a demo library slug (matches meals.recipe_detail), else None."""
    row = next((x for x in _DEMO_RECIPES if x[0] == slug), None)
    if row is None:
        return None
    s, name, total, *_ = row
    return {"available": True, "recipe": {
        "slug": s, "id": None, "name": name, "has_image": False, "servings": 4,
        "prep": "10 Minutes", "cook": total, "total": total,
        "description": f"A family staple: {name.lower()} with simple ingredients.",
        "ingredients": [{"heading": "Main"}, {"text": "1 pound the main ingredient"}, {"text": "2 cups something hearty"},
                        {"text": "1 teaspoon salt"}, {"heading": "To finish"}, {"text": "Fresh herbs, chopped"}],
        "steps": [{"title": None, "text": "Prepare everything before you start."},
                  {"title": "Cook", "text": "Combine the ingredients and cook until done.\nStir now and then."},
                  {"title": None, "text": "Season to taste and serve hot."}],
        "notes": [{"title": "Tip", "text": "It reheats well, so make extra."}]}}
```

- [ ] **Step 5: Run to verify they pass, then both files**

Run: `... -m pytest tests/test_meals.py tests/test_demo.py -q`
Expected: all pass.

- [ ] **Step 6: Changelog bullet and commit**

```markdown
- Recipes: demo mode serves a canned twelve-recipe library with detail pages, so the Recipes
  view shows every state (categories, never-made and unrated recipes, section headings, notes).
```
```bash
git add CHANGELOG.md src/family_hub/app.py src/family_hub/demo.py tests/test_meals.py tests/test_demo.py
git commit -m "feat(meals): recipe routes, the photo size option and demo data"
```

---

### Task 5: Filter, sort and idle logic (pure, in `common.js`)

**Files:**
- Modify: `src/family_hub/web/static/common.js` (after `idleReturnMs`)
- Test: `tests/js/hub.test.mjs` (add to the destructured list and new tests)

**Interfaces:**
- Consumes: nothing (pure functions; `common.js` is a classic script).
- Produces: `RECIPE_SORTS` = `[['name','A to Z'],['added','Recently added'],['made','Recently made'],['rated','Top rated']]`; `recipeFilter(recipes, query, category)`; `recipeSort(recipes, key)`; `recipeCategories(recipes)` -> sorted unique names; `idleReturnMs('recipes') === 900000`.

- [ ] **Step 1: Write the failing tests.** In `tests/js/hub.test.mjs` add `recipeFilter, recipeSort, recipeCategories, RECIPE_SORTS,` to the destructuring from `sandbox`, then append:

```js
// ---- the Recipes view: filter, sort, categories, idle ----

const R = (name, o = {}) => ({ slug: name.toLowerCase().replace(/ /g, '-'), name, categories: [], tags: [],
  added: null, made: null, rating: null, ...o });
const names = (list) => Array.from(list, (r) => r.name);   // main-realm array: deepEqual compares prototypes, and common.js runs in a vm

test('recipeFilter: matches name, categories and tags, case-insensitively and trimmed', () => {
  const list = [R('Baked Ziti', { categories: ['Dinner'], tags: ['Family favourite'] }),
    R('Pancakes', { categories: ['Breakfast'] }), R('Cookies', { tags: ['Kids'] })];
  assert.deepEqual(names(recipeFilter(list, '  ZITI ', '')), ['Baked Ziti']);
  assert.deepEqual(names(recipeFilter(list, 'breakfast', '')), ['Pancakes']);
  assert.deepEqual(names(recipeFilter(list, 'kid', '')), ['Cookies']);
  assert.deepEqual(names(recipeFilter(list, '', '')), ['Baked Ziti', 'Pancakes', 'Cookies']);
  assert.deepEqual(names(recipeFilter(list, 'zzz', '')), []);
});

test('recipeFilter: a category and a search combine; All (empty) is no category', () => {
  const list = [R('Soup', { categories: ['Dinner'] }), R('Salad', { categories: ['Lunch'] }), R('Stew', { categories: ['Dinner'] })];
  assert.deepEqual(names(recipeFilter(list, '', 'Dinner')), ['Soup', 'Stew']);
  assert.deepEqual(names(recipeFilter(list, 'st', 'Dinner')), ['Stew']);
  assert.deepEqual(names(recipeFilter(list, 'salad', 'Dinner')), []);
});

test('recipeFilter: never throws on odd recipes or input', () => {
  assert.deepEqual(recipeFilter([], 'x', 'y'), []);
  assert.deepEqual(names(recipeFilter([R('A')], null, undefined)), ['A']);
  assert.deepEqual(names(recipeFilter([{ name: 'No lists' }], 'no', '')), ['No lists']);
});

test('recipeSort: A to Z ignores case and is the default', () => {
  const list = [R('banana'), R('Apple'), R('cherry')];
  assert.deepEqual(names(recipeSort(list, 'name')), ['Apple', 'banana', 'cherry']);
  assert.deepEqual(names(recipeSort(list, 'whatever')), ['Apple', 'banana', 'cherry']);
});

test('recipeSort: recently added puts the newest first, undated last, ties by name', () => {
  const list = [R('Old', { added: '2026-01-01T00:00:00+00:00' }), R('None'), R('New', { added: '2026-09-01T00:00:00+00:00' }),
    R('Also New', { added: '2026-09-01T00:00:00+00:00' })];
  assert.deepEqual(names(recipeSort(list, 'added')), ['Also New', 'New', 'Old', 'None']);
});

test('recipeSort: recently made puts never-made recipes last, A to Z', () => {
  const list = [R('Never B'), R('Long ago', { made: '2026-01-01' }), R('Never A'), R('Yesterday', { made: '2026-10-04' })];
  assert.deepEqual(names(recipeSort(list, 'made')), ['Yesterday', 'Long ago', 'Never A', 'Never B']);
});

test('recipeSort: top rated is high to low, unrated (and zero) last, ties by name', () => {
  const list = [R('Three', { rating: 3 }), R('Zero', { rating: 0 }), R('Five B', { rating: 5 }), R('Unrated'), R('Five A', { rating: 5 }), R('Half', { rating: 4.5 })];
  assert.deepEqual(names(recipeSort(list, 'rated')), ['Five A', 'Five B', 'Half', 'Three', 'Unrated', 'Zero']);
});

test('recipeSort: does not modify its input and survives unparseable dates', () => {
  const list = [R('B', { added: 'garbage' }), R('A', { added: '2026-01-01' })];
  const copy = names(list);
  assert.deepEqual(names(recipeSort(list, 'added')), ['A', 'B']);
  assert.deepEqual(names(list), copy);
});

test('recipeCategories: unique names, A to Z, from every recipe', () => {
  const list = [R('a', { categories: ['Dinner', 'Soup'] }), R('b', { categories: ['dessert', 'Dinner'] }), R('c')];
  assert.deepEqual(Array.from(recipeCategories(list)), ['dessert', 'Dinner', 'Soup']);
  assert.deepEqual(Array.from(recipeCategories([])), []);
});

test('RECIPE_SORTS lists the four sorts with A to Z first', () => {
  assert.deepEqual(Array.from(RECIPE_SORTS, (s) => s[0]), ['name', 'added', 'made', 'rated']);
});

test('idleReturnMs: the Recipes view gets 15 minutes (someone is cooking from it)', () => {
  assert.equal(idleReturnMs('recipes'), 900000);
  assert.ok(idleReturnMs('recipes') > idleReturnMs('camera'));
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/hub.test.mjs`
Expected: FAIL (`recipeFilter is not a function` / `idleReturnMs('recipes')` is 90000).

- [ ] **Step 3: Implement** (`common.js`). Change `idleReturnMs`:

```js
function idleReturnMs(view) {
  if (view && view.indexOf('camera') === 0) return 300000;  // camera, camera:<src>
  if (view === 'calendar') return 180000;
  if (view === 'recipes') return 900000;   // someone cooking from a recipe is not idle
  return 90000;
}
```
and add after it:

```js
/* ---- Recipes view: filter, sort, categories (pure, run on the loaded list) ---------- */
const RECIPE_SORTS = [['name', 'A to Z'], ['added', 'Recently added'], ['made', 'Recently made'], ['rated', 'Top rated']];

function recipeFilter(recipes, query, category) {
  const q = String(query == null ? '' : query).trim().toLowerCase();
  const list = Array.isArray(recipes) ? recipes : [];
  return list.filter((r) => {
    if (!r) return false;
    const cats = Array.isArray(r.categories) ? r.categories : [];
    const tags = Array.isArray(r.tags) ? r.tags : [];
    if (category && !cats.includes(category)) return false;
    if (!q) return true;
    return [r.name, ...cats, ...tags].some((s) => typeof s === 'string' && s.toLowerCase().includes(q));
  });
}

function recipeSort(recipes, key) {
  const byName = (a, b) => String(a.name).localeCompare(String(b.name), undefined, { sensitivity: 'base' });
  const when = (v) => { const t = Date.parse(v); return Number.isFinite(t) ? t : null; };
  const stars = (r) => (Number.isFinite(r.rating) && r.rating > 0 ? r.rating : null);
  // newest/highest first; recipes with no value last; ties and the no-value group A to Z
  const desc = (get) => (a, b) => {
    const x = get(a); const y = get(b);
    if (x === null && y === null) return byName(a, b);
    if (x === null) return 1;
    if (y === null) return -1;
    return (y - x) || byName(a, b);
  };
  const list = (Array.isArray(recipes) ? recipes : []).slice();
  if (key === 'added') return list.sort(desc((r) => when(r.added)));
  if (key === 'made') return list.sort(desc((r) => when(r.made)));
  if (key === 'rated') return list.sort(desc(stars));
  return list.sort(byName);
}

function recipeCategories(recipes) {
  const seen = new Set();
  (Array.isArray(recipes) ? recipes : []).forEach((r) => {
    ((r && Array.isArray(r.categories)) ? r.categories : []).forEach((c) => { if (typeof c === 'string' && c) seen.add(c); });
  });
  return [...seen].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}
```

- [ ] **Step 4: Run to verify they pass, then all JS**

Run: `node --test tests/js/*.mjs`
Expected: all pass.

- [ ] **Step 5: Changelog bullet and commit**

```markdown
- Recipes: search, category filter and four sorts (A to Z, recently added, recently made, top
  rated) run on the loaded library, so typing never waits on the network; the Recipes view
  stays open 15 minutes without a touch (the wall's default is 90 seconds).
```
```bash
git add CHANGELOG.md src/family_hub/web/static/common.js tests/js/hub.test.mjs
git commit -m "feat(wall): recipe filter, sort and category logic, 15-minute idle for Recipes"
```

---

### Task 6: The Recipes overlay (grid, controls, detail)

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (state + view block before `let fitDebounce`; `openOverlay` branch; click/input/error wiring)
- Modify: `src/family_hub/web/static/styles.css` (new block after the Shopping styles)
- Test: `tests/js/hub-dom.test.mjs` (add `'recipes-full'` to `SEEDED_IDS`; new tests)

**Interfaces:**
- Consumes: Task 5's `RECIPE_SORTS`, `recipeFilter`, `recipeSort`, `recipeCategories`; `j`, `escapeHtml`, `showToast`, `openOverlay`'s `content`; endpoints from Task 4.
- Produces: global `recipesState`; `recipesReset()`, `renderRecipes()`, `updateRecipesGrid()`, `recipeCardHtml(r)`, `recipeDetailHtml()`, `fetchRecipes()`, `openRecipe(slug)`, `recipesBack()`; `openOverlay('recipes')`. Markup contract: `#recipes-full` inside `.overlay-panel`; the grid screen is `.recipes` > `.overlay-title`, `.recipes-bar` (> `input#recipe-search.txt-input`), `#recipes-controls`, `#recipes-grid`; cards are `button.recipe-card[data-recipe-open=<slug>]`; sort buttons `[data-recipe-sort=<key>]`; chips `[data-recipe-cat=<name or "">]`; detail has `button.recipe-back[data-recipe-back]`; retry `[data-recipe-retry]`.

- [ ] **Step 1: Write the failing tests.** Add `'recipes-full'` to `SEEDED_IDS` (line ~36). Append to `tests/js/hub-dom.test.mjs`:

```js
// ---- the Recipes overlay ----

const rcp = (slug, name, o = {}) => ({ slug, id: null, name, time: '30 Minutes', has_image: false,
  categories: ['Dinner'], tags: [], added: '2026-09-01T00:00:00+00:00', made: null, rating: null, ...o });
const RCP_LIST = () => ({ available: true, truncated: false, total: 4, recipes: [
  rcp('apple-pie', 'Apple Pie', { categories: ['Dessert'], added: '2026-10-01T00:00:00+00:00' }),
  rcp('baked-ziti', 'Baked Ziti', { id: RID_A, has_image: true, made: '2026-10-03', rating: 5 }),
  rcp('chili', 'Chili', { time: null }),
  rcp('oats', 'Overnight Oats', { categories: ['Breakfast'] })] });
const RCP_DETAIL = (over = {}) => ({ available: true, recipe: { slug: 'baked-ziti', id: RID_A, name: 'Baked Ziti',
  has_image: true, servings: 6, prep: '15 Minutes', cook: '45 Minutes', total: '1 Hour', description: 'Cheesy pasta.',
  ingredients: [{ heading: 'Sauce' }, { text: '1 can tomatoes' }], steps: [{ title: 'Boil', text: 'Boil the pasta.\nDrain.' }],
  notes: [{ title: 'Tip', text: 'Use basil.' }], ...over } });

function rcpFetch(sandbox, { list = RCP_LIST(), detail = RCP_DETAIL(), failList = false, failDetail = false } = {}) {
  const calls = [];
  sandbox.fetch = async (url) => {
    calls.push(url);
    if (url === '/api/mealie/recipes') {
      return failList ? { ok: false, status: 502, json: async () => ({ detail: 'down' }) } : { ok: true, status: 200, json: async () => list };
    }
    if (url.startsWith('/api/mealie/recipes/')) {
      return failDetail ? { ok: false, status: 404, json: async () => ({ detail: 'no such recipe' }) } : { ok: true, status: 200, json: async () => detail };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
  return calls;
}

async function rcpOpen(opts) {
  const hub = newHub();
  vm.runInContext(LISTED, hub.sandbox);
  const calls = rcpFetch(hub.sandbox, opts);
  hub.sandbox.openOverlay('recipes');
  await flush(); await flush();
  return { ...hub, calls, host: hub.document.getElementById('recipes-full') };
}
const rcpCards = (host) => host.querySelectorAll('.recipe-card').map((c) => c.dataset.recipeOpen);
const tapRcp = (fire, host, sel, attr) => {
  const btn = host.querySelector(sel);
  assert.ok(btn, `${sel} rendered`);
  btn.closest = (s) => (s === `[${attr}]` ? btn : null);
  fire('click', { target: btn, preventDefault() {} });
  return btn;
};

test('Recipes: opening the overlay shows the grid A to Z with every control, and fetches the library once', async () => {
  const { host, calls } = await rcpOpen();
  assert.deepEqual(rcpCards(host), ['apple-pie', 'baked-ziti', 'chili', 'oats']);
  assert.equal(calls.filter((u) => u === '/api/mealie/recipes').length, 1);
  assert.match(host.innerHTML, /id="recipe-search" class="txt-input recipes-search"/, 'the on-screen keyboard serves .txt-input');
  assert.equal(host.querySelectorAll('[data-recipe-sort]').length, 4);
  assert.deepEqual(host.querySelectorAll('[data-recipe-cat]').map((b) => b.dataset.recipeCat), ['', 'Breakfast', 'Dessert', 'Dinner']);
  assert.match(host.innerHTML, /data-recipe-sort="name" aria-pressed="true"/);
});

test('Recipes: a card shows its thumbnail (tiny, lazy), name and time; no photo or no time degrades cleanly', async () => {
  const { host } = await rcpOpen();
  assert.match(host.innerHTML, new RegExp(`<img class="recipe-thumb" src="/api/mealie/image/${RID_A}\\?size=tiny" alt="" loading="lazy" decoding="async">`));
  assert.match(host.innerHTML, /recipe-noimg/);
  assert.match(host.innerHTML, /<span class="recipe-time">30 Minutes<\/span>/);
  const chili = host.querySelectorAll('.recipe-card').find((c) => c.dataset.recipeOpen === 'chili');
  assert.doesNotMatch(chili.innerHTML, /recipe-time/);
});

test('Recipes: typing filters the cards and NEVER repaints the search box', async () => {
  const { sandbox, fire, host } = await rcpOpen();
  const box = host.querySelector('#recipe-search');
  box.value = 'zit';
  fire('input', { target: { id: 'recipe-search', value: 'zit' } });
  assert.deepEqual(rcpCards(host), ['baked-ziti']);
  assert.strictEqual(host.querySelector('#recipe-search'), box, 'the same input element: focus and keyboard survive');
  fire('input', { target: { id: 'recipe-search', value: 'nothing matches' } });
  assert.match(host.innerHTML, /No recipes match/);
  assert.equal(vm.runInContext('recipesState.q', sandbox), 'nothing matches');
});

test('Recipes: a sort button re-orders, the active one is pressed; a chip filters and combines with search', async () => {
  const { fire, host } = await rcpOpen();
  tapRcp(fire, host, '[data-recipe-sort="rated"]', 'data-recipe-sort');
  assert.deepEqual(rcpCards(host).slice(0, 1), ['baked-ziti'], 'top rated first');
  assert.match(host.innerHTML, /data-recipe-sort="rated" aria-pressed="true"/);
  tapRcp(fire, host, '[data-recipe-sort="made"]', 'data-recipe-sort');
  assert.equal(rcpCards(host)[0], 'baked-ziti', 'recently made first, never-made after');
  tapRcp(fire, host, '[data-recipe-cat="Dinner"]', 'data-recipe-cat');
  assert.deepEqual(rcpCards(host), ['baked-ziti', 'chili']);
  fire('input', { target: { id: 'recipe-search', value: 'chi' } });
  assert.deepEqual(rcpCards(host), ['chili']);
  tapRcp(fire, host, '[data-recipe-cat=""]', 'data-recipe-cat');
  assert.deepEqual(rcpCards(host), ['chili'], 'All keeps the search');
});

test('Recipes: tapping a card shows the detail; Back restores search, sort, category and scroll', async () => {
  const { sandbox, fire, host } = await rcpOpen();
  tapRcp(fire, host, '[data-recipe-sort="added"]', 'data-recipe-sort');
  tapRcp(fire, host, '[data-recipe-cat="Dinner"]', 'data-recipe-cat');
  fire('input', { target: { id: 'recipe-search', value: 'ziti' } });
  host.parentNode = { scrollTop: 340 };
  tapRcp(fire, host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  assert.match(host.innerHTML, /<h2[^>]*>Baked Ziti<\/h2>/);
  assert.match(host.innerHTML, /Cheesy pasta\./);
  assert.match(host.innerHTML, /class="recipe-ing-head">Sauce</);
  assert.match(host.innerHTML, /<li>1 can tomatoes<\/li>/);
  assert.match(host.innerHTML, /Boil the pasta\.<br>Drain\./, 'step line breaks are kept');
  assert.match(host.innerHTML, /Use basil\./);
  assert.match(host.innerHTML, new RegExp(`/api/mealie/image/${RID_A}"`), 'the detail photo is the medium size');
  tapRcp(fire, host, '[data-recipe-back]', 'data-recipe-back');
  assert.equal(host.querySelector('#recipe-search').value, 'ziti');
  assert.deepEqual(rcpCards(host), ['baked-ziti']);
  assert.match(host.innerHTML, /data-recipe-sort="added" aria-pressed="true"/);
  assert.match(host.innerHTML, /data-recipe-cat="Dinner" aria-pressed="true"/);
  assert.equal(host.parentNode.scrollTop, 340);
  assert.equal(vm.runInContext('recipesState.slug', sandbox), null);
});

test('Recipes: the detail shows only the meta it has', async () => {
  const { fire, host } = await rcpOpen({ detail: RCP_DETAIL({ prep: null, cook: null, servings: null, total: '1 Hour', notes: [], description: '', has_image: false }) });
  tapRcp(fire, host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  assert.match(host.innerHTML, /<dt>Total<\/dt>/);
  assert.doesNotMatch(host.innerHTML, /<dt>Prep<\/dt>|<dt>Cook<\/dt>|<dt>Serves<\/dt>|recipe-photo|Notes/);
});

test('Recipes: everything from Mealie is inert text', async () => {
  const evil = '<img src=x onerror=alert(1)>';
  const list = { available: true, truncated: false, total: 1, recipes: [rcp('x', evil, { categories: [evil], tags: [evil], time: evil })] };
  const { fire, host } = await rcpOpen({ list, detail: RCP_DETAIL({ name: evil, description: evil,
    ingredients: [{ heading: evil }, { text: evil }], steps: [{ title: evil, text: evil }], notes: [{ title: evil, text: evil }], prep: evil }) });
  assert.doesNotMatch(host.innerHTML, /<img src=x/);
  assert.match(host.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  tapRcp(fire, host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  assert.doesNotMatch(host.innerHTML, /<img src=x/);
  assert.match(host.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('Recipes: a recipe that is gone gives a toast and keeps the grid (never a stuck Loading)', async () => {
  const { document, fire, host } = await rcpOpen({ failDetail: true });
  tapRcp(fire, host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  assert.equal(document.getElementById('toast').textContent, 'no such recipe');
  assert.deepEqual(rcpCards(host), ['apple-pie', 'baked-ziti', 'chili', 'oats']);
  assert.doesNotMatch(host.innerHTML, /Loading/);
});

test('Recipes: a late older detail reply never overwrites a newer one; Back during a load wins', async () => {
  const { sandbox, fire, host } = await rcpOpen();
  const slow = {}; slow.p = new Promise((r) => { slow.release = r; });
  let n = 0;
  sandbox.fetch = async (url) => {
    if (!url.startsWith('/api/mealie/recipes/')) return { ok: true, status: 200, json: async () => RCP_LIST() };
    n += 1;
    if (n === 1) { await slow.p; return { ok: true, status: 200, json: async () => RCP_DETAIL({ name: 'OLD' }) }; }
    return { ok: true, status: 200, json: async () => RCP_DETAIL({ name: 'NEW' }) };
  };
  tapRcp(fire, host, '[data-recipe-open="apple-pie"]', 'data-recipe-open');   // first, slow
  await flush();
  tapRcp(fire, host, '[data-recipe-back]', 'data-recipe-back');
  tapRcp(fire, host, '[data-recipe-open="chili"]', 'data-recipe-open');        // second, fast
  await flush(); await flush();
  slow.release(); await flush(); await flush();
  assert.match(host.innerHTML, />NEW</); assert.doesNotMatch(host.innerHTML, /OLD/);
  tapRcp(fire, host, '[data-recipe-back]', 'data-recipe-back');
  assert.equal(vm.runInContext('recipesState.slug', sandbox), null);
});

test('Recipes: a late older LIST reply never overwrites a newer one', async () => {
  const { sandbox, host } = await rcpOpen();
  const slow = {}; slow.p = new Promise((r) => { slow.release = r; });
  let n = 0;
  sandbox.fetch = async () => {
    n += 1;
    if (n === 1) { await slow.p; return { ok: true, status: 200, json: async () => ({ ...RCP_LIST(), recipes: [rcp('old-one', 'OLD')] }) }; }
    return { ok: true, status: 200, json: async () => ({ ...RCP_LIST(), recipes: [rcp('new-one', 'NEW')] }) };
  };
  const first = sandbox.fetchRecipes();
  await sandbox.fetchRecipes();
  slow.release(); await first;
  assert.deepEqual(rcpCards(host), ['new-one']);
});

test('Recipes: Mealie down, a refused token and an empty library each say so; Try again re-reads', async () => {
  let r = await rcpOpen({ failList: true });
  assert.match(r.host.innerHTML, /Mealie isn.t reachable/);
  assert.ok(r.host.querySelector('[data-recipe-retry]'));
  r = await rcpOpen({ list: { available: false, needs_auth: true } });
  assert.match(r.host.innerHTML, /Needs a Mealie token/);
  r = await rcpOpen({ list: { available: true, truncated: false, total: 0, recipes: [] } });
  assert.match(r.host.innerHTML, /No recipes yet/);
  r = await rcpOpen({ failList: true });
  const before = r.calls.length;
  tapRcp(r.fire, r.host, '[data-recipe-retry]', 'data-recipe-retry');
  await flush(); await flush();
  assert.ok(r.calls.length > before, 'a retry asks again');
});

test('Recipes: a library past the cap says how many are shown', async () => {
  const { host } = await rcpOpen({ list: { ...RCP_LIST(), truncated: true, total: 340 } });
  assert.match(host.innerHTML, /Showing the first 4 of 340/);
});

test('Recipes: opening the view again starts fresh (no leftover search, sort, category or recipe)', async () => {
  const { sandbox, fire, host } = await rcpOpen();
  fire('input', { target: { id: 'recipe-search', value: 'ziti' } });
  tapRcp(fire, host, '[data-recipe-sort="rated"]', 'data-recipe-sort');
  sandbox.closeOverlay();
  sandbox.openOverlay('recipes');
  await flush(); await flush();
  assert.equal(vm.runInContext('recipesState.q', sandbox), '');
  assert.equal(vm.runInContext('recipesState.sort', sandbox), 'name');
  assert.deepEqual(rcpCards(host), ['apple-pie', 'baked-ziti', 'chili', 'oats']);
});

test('Recipes: a thumbnail that fails to load is hidden, leaving the placeholder tile', () => {
  const { fire } = newHub();
  const img = { tagName: 'IMG', classList: { contains: (c) => c === 'recipe-thumb', add(c) { this.added = c; } } };
  fire('error', { target: img });
  assert.equal(img.classList.added, 'is-broken');
  const other = { tagName: 'IMG', classList: { contains: () => false, add() { throw new Error('touched'); } } };
  fire('error', { target: other });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/hub-dom.test.mjs`
Expected: FAIL (`openOverlay('recipes')` builds nothing; `fetchRecipes is not a function`).

- [ ] **Step 3: Add the state and view code** (`hub.js`, directly before `let fitDebounce = null;`):

```js
/* ------------------------------------------------------------ Recipes view */

/* The native Mealie recipes view (operator, 2026-10-06): a full-screen overlay opened from the
   Dinner card's Recipes button, replacing the slow Mealie iframe. It loads every recipe summary
   in one request and filters/sorts on the screen (common.js: recipeFilter/recipeSort), so typing
   never waits on the network. Typing and chips redraw only the card area (#recipes-controls and
   #recipes-grid), never the search box, so the on-screen keyboard keeps focus. */

const recipesState = {
  data: null,        // last /api/mealie/recipes payload
  seq: 0,            // numbers list fetches so a late older reply never overwrites a newer one
  q: '', sort: 'name', cat: '',
  slug: null,        // the recipe open in the detail screen, or null for the grid
  detail: null,      // that recipe's detail, once it has loaded
  detailSeq: 0,
  scroll: 0,         // the grid's scroll position, restored on Back
};

function recipesReset() {
  Object.assign(recipesState, { data: null, q: '', sort: 'name', cat: '', slug: null, detail: null, scroll: 0 });
  recipesState.seq += 1;
  recipesState.detailSeq += 1;
}

function recipesHost() { return document.getElementById('recipes-full'); }

function recipeCardHtml(r) {
  const thumb = r.has_image && r.id
    ? `<img class="recipe-thumb" src="/api/mealie/image/${escapeHtml(r.id)}?size=tiny" alt="" loading="lazy" decoding="async">`
    : `<span class="recipe-thumb recipe-noimg" aria-hidden="true">🍽</span>`;
  return `<button type="button" class="recipe-card" data-recipe-open="${escapeHtml(r.slug)}">${thumb}`
    + `<span class="recipe-name">${escapeHtml(r.name)}</span>`
    + (r.time ? `<span class="recipe-time">${escapeHtml(r.time)}</span>` : '') + `</button>`;
}

function recipesControlsHtml(all) {
  const s = recipesState;
  const sorts = RECIPE_SORTS.map(([key, label]) =>
    `<button type="button" class="recipe-sort${s.sort === key ? ' on' : ''}" data-recipe-sort="${key}"`
    + ` aria-pressed="${s.sort === key}">${escapeHtml(label)}</button>`).join('');
  const chip = (name, label) => `<button type="button" class="recipe-chip${s.cat === name ? ' on' : ''}"`
    + ` data-recipe-cat="${escapeHtml(name)}" aria-pressed="${s.cat === name}">${escapeHtml(label)}</button>`;
  const cats = recipeCategories(all);
  return `<div class="recipes-sorts">${sorts}</div>`
    + (cats.length ? `<div class="recipes-chips">${chip('', 'All')}${cats.map((c) => chip(c, c)).join('')}</div>` : '');
}

function recipesGridNote(d) {
  const retry = `<button type="button" class="recipe-sort" data-recipe-retry>Try again</button>`;
  if (d == null) return `<div class="recipes-note">Loading…</div>`;
  if (!d.available) {
    return `<div class="recipes-note">${d.needs_auth ? 'Needs a Mealie token' : 'Mealie isn’t reachable'} ${retry}</div>`;
  }
  return '';
}

/* Redraw the sort buttons, chips and cards from the loaded list. Never touches the search box. */
function updateRecipesGrid() {
  const host = recipesHost();
  if (!host || typeof host.querySelector !== 'function') return;
  const controls = host.querySelector('#recipes-controls');
  const grid = host.querySelector('#recipes-grid');
  if (!controls || !grid) return;
  const d = recipesState.data;
  const note = recipesGridNote(d);
  if (note) { controls.innerHTML = ''; grid.innerHTML = note; return; }
  const all = Array.isArray(d.recipes) ? d.recipes : [];
  controls.innerHTML = recipesControlsHtml(all);
  const shown = recipeSort(recipeFilter(all, recipesState.q, recipesState.cat), recipesState.sort);
  grid.innerHTML = (all.length === 0 ? `<div class="recipes-note">No recipes yet</div>`
    : shown.length === 0 ? `<div class="recipes-note">No recipes match</div>`
    : `<div class="recipe-grid">${shown.map(recipeCardHtml).join('')}</div>`)
    + (d.truncated ? `<div class="recipes-note">Showing the first ${all.length} of ${Number(d.total) || all.length}</div>` : '');
}

function recipeParasHtml(text) {
  return escapeHtml(String(text || '')).replace(/\n/g, '<br>');
}

function recipeDetailHtml() {
  const d = recipesState.detail;
  const back = `<button type="button" class="recipe-back" data-recipe-back>← Recipes</button>`;
  if (!d) return `<div class="recipes">${back}<div class="recipes-note">Loading…</div></div>`;
  const photo = d.has_image && d.id
    ? `<img class="recipe-photo" src="/api/mealie/image/${escapeHtml(d.id)}" alt="">` : '';
  const meta = [['Prep', d.prep], ['Cook', d.cook], ['Total', d.total], ['Serves', d.servings]]
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`).join('');
  const ings = (d.ingredients || []).map((i) => (i.heading
    ? `<li class="recipe-ing-head">${escapeHtml(i.heading)}</li>` : `<li>${escapeHtml(i.text)}</li>`)).join('');
  const steps = (d.steps || []).map((s) => `<li>${s.title ? `<strong>${escapeHtml(s.title)}</strong> ` : ''}`
    + `${recipeParasHtml(s.text)}</li>`).join('');
  const notes = (d.notes || []).map((n) => `<div class="recipe-note-item">`
    + `${n.title ? `<strong>${escapeHtml(n.title)}</strong> ` : ''}${recipeParasHtml(n.text)}</div>`).join('');
  return `<div class="recipes">${back}<article class="recipe-detail">`
    + `<div class="recipe-side">${photo}${meta ? `<dl class="recipe-meta">${meta}</dl>` : ''}</div>`
    + `<div class="recipe-main"><h2>${escapeHtml(d.name)}</h2>`
    + (d.description ? `<p class="recipe-desc">${escapeHtml(d.description)}</p>` : '')
    + (ings ? `<h3>Ingredients</h3><ul class="recipe-ings">${ings}</ul>` : '')
    + (steps ? `<h3>Steps</h3><ol class="recipe-steps">${steps}</ol>` : '')
    + (notes ? `<h3>Notes</h3><div class="recipe-notes">${notes}</div>` : '')
    + `</div></article></div>`;
}

function recipesGridShellHtml() {
  return `<div class="recipes"><div class="overlay-title">Recipes</div>`
    + `<div class="recipes-bar"><input id="recipe-search" class="txt-input recipes-search" type="text" maxlength="60"`
    + ` placeholder="Search recipes…" autocomplete="off" aria-label="Search recipes" value="${escapeHtml(recipesState.q)}"></div>`
    + `<div id="recipes-controls"></div><div id="recipes-grid"></div></div>`;
}

function renderRecipes() {
  const host = recipesHost();
  if (!host) return;
  const panel = host.parentNode;
  if (recipesState.slug) {
    host.innerHTML = recipeDetailHtml();
    if (panel) panel.scrollTop = 0;
    return;
  }
  host.innerHTML = recipesGridShellHtml();
  updateRecipesGrid();
  if (panel && recipesState.scroll) panel.scrollTop = recipesState.scroll;
}

async function fetchRecipes() {
  const seq = ++recipesState.seq;
  let res;
  try {
    res = await j('/api/mealie/recipes');
  } catch (e) {
    res = { available: false };
  }
  if (seq !== recipesState.seq) return;            // a newer read (or a reopen) owns the screen
  recipesState.data = res && typeof res === 'object' ? res : { available: false };
  if (recipesState.slug) return;                    // reading a recipe: the list is there on Back
  const host = recipesHost();
  if (host && typeof host.querySelector === 'function' && host.querySelector('#recipes-grid')) updateRecipesGrid();
  else renderRecipes();
}

async function openRecipe(slug) {
  const host = recipesHost();
  const panel = host && host.parentNode;
  if (!recipesState.slug) recipesState.scroll = panel ? panel.scrollTop || 0 : 0;
  const seq = ++recipesState.detailSeq;
  recipesState.slug = slug;
  recipesState.detail = null;
  renderRecipes();
  let res;
  try {
    res = await j(`/api/mealie/recipes/${encodeURIComponent(slug)}`);
  } catch (e) {
    res = { available: false, error: e && e.message };
  }
  if (seq !== recipesState.detailSeq || recipesState.slug !== slug) return;   // Back, or another card
  if (!res || !res.available || !res.recipe) {
    showToast(res && res.needs_auth ? 'Needs a Mealie token' : ((res && res.error) || 'Could not load that recipe'));
    recipesState.slug = null;
    renderRecipes();
    return;
  }
  recipesState.detail = res.recipe;
  renderRecipes();
}

function recipesBack() {
  recipesState.detailSeq += 1;                      // abandon a detail still loading
  recipesState.slug = null;
  recipesState.detail = null;
  renderRecipes();
}

document.addEventListener('input', (e) => {
  if (e.target && e.target.id === 'recipe-search') {
    recipesState.q = e.target.value;
    updateRecipesGrid();
  }
});

// a thumbnail that fails to load becomes the placeholder tile, not a broken-image icon;
// error does not bubble, so listen in the capture phase
document.addEventListener('error', (e) => {
  const t = e.target;
  if (t && t.tagName === 'IMG' && t.classList && t.classList.contains('recipe-thumb')) t.classList.add('is-broken');
}, true);
```

- [ ] **Step 4: Wire the overlay and the clicks** (`hub.js`). In `openOverlay`, add this branch directly BEFORE the existing `view === 'meals-full'` branch (leave `meals-full` in place for now: its old tests are replaced and the branch removed together in Task 7, so the suite stays green between the two tasks):

```js
  } else if (view === 'recipes') {
    content.innerHTML = `<div class="overlay-panel"><div id="recipes-full"></div></div>`;
    recipesReset();
    renderRecipes();
    fetchRecipes();
```
(Insert these lines immediately above the line `  } else if (view === 'meals-full') {`; that existing line then closes the new branch.)
In the document `click` handler, directly after the Shopping handlers (`shopDelBtn`), add:

```js
  const rcOpen = e.target.closest('[data-recipe-open]');
  if (rcOpen) { openRecipe(rcOpen.dataset.recipeOpen); return; }
  const rcBack = e.target.closest('[data-recipe-back]');
  if (rcBack) { recipesBack(); return; }
  const rcSort = e.target.closest('[data-recipe-sort]');
  if (rcSort) { recipesState.sort = rcSort.dataset.recipeSort; updateRecipesGrid(); return; }
  const rcCat = e.target.closest('[data-recipe-cat]');
  if (rcCat) { recipesState.cat = rcCat.dataset.recipeCat; updateRecipesGrid(); return; }
  const rcRetry = e.target.closest('[data-recipe-retry]');
  if (rcRetry) { fetchRecipes(); return; }
```

- [ ] **Step 5: Add the CSS** (`styles.css`, after the Shopping block, before the `.fleet` rules or at the end of the Meals section). No `backdrop-filter`, no animation, no transition:

```css
/* ---- native Recipes view (opened from the Dinner card): grid, filters, detail ---- */
.recipes { display: flex; flex-direction: column; gap: 14px; max-width: 1840px; margin: 0 auto; }
.recipes .overlay-title { margin: 0; }
.recipes-bar { display: flex; gap: 10px; }
.recipes-search { flex: 1; min-width: 0; font-size: 18px; }
.recipes-sorts, .recipes-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.recipe-sort, .recipe-chip { font: inherit; font-size: 14px; font-weight: 600; color: var(--ink); cursor: pointer;
  background: var(--surface-2); border: 1px solid var(--edge); border-radius: 999px; padding: 10px 16px; min-height: 44px; }
.recipe-sort.on, .recipe-chip.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.recipe-sort:focus-visible, .recipe-chip:focus-visible, .recipe-card:focus-visible, .recipe-back:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px; }
.recipe-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.recipe-card { display: flex; flex-direction: column; gap: 8px; min-width: 0; padding: 0 0 12px; overflow: hidden;
  text-align: left; font: inherit; color: var(--ink); cursor: pointer;
  background: var(--surface); border: 1px solid var(--edge); border-radius: 14px; }
.recipe-thumb { display: block; width: 100%; aspect-ratio: 1 / 1; object-fit: cover; background: var(--surface-2); }
.recipe-noimg { display: flex; align-items: center; justify-content: center; font-size: 44px; }
.recipe-thumb.is-broken { visibility: hidden; }
.recipe-name { padding: 0 12px; font-size: 16px; font-weight: 600; line-height: 1.25; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
.recipe-time { padding: 0 12px; font-size: 13px; color: var(--dim); }
.recipes-note { padding: 18px 4px; font-size: 16px; color: var(--dim); }
.recipe-back { align-self: flex-start; font: inherit; font-size: 15px; font-weight: 600; color: var(--ink); cursor: pointer;
  background: var(--surface-2); border: 1px solid var(--edge); border-radius: 999px; padding: 10px 18px; min-height: 44px; }
.recipe-detail { display: grid; grid-template-columns: minmax(260px, 520px) minmax(0, 1fr); gap: 32px; align-items: start; }
.recipe-photo { display: block; width: 100%; max-height: 70vh; object-fit: cover; border-radius: 14px; background: var(--surface-2); }
.recipe-meta { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 14px 0 0; }
.recipe-meta dt { font-family: var(--mono); font-size: 11px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--dim); }
.recipe-meta dd { margin: 2px 0 0; font-size: 18px; }
.recipe-main { min-width: 0; font-size: 20px; line-height: 1.5; }
.recipe-main h2 { margin: 0 0 8px; font-size: 32px; line-height: 1.2; overflow-wrap: anywhere; }
.recipe-main h3 { margin: 24px 0 8px; font-family: var(--mono); font-size: 13px; font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: var(--dim); }
.recipe-desc { margin: 0; color: var(--dim); }
.recipe-ings, .recipe-steps { margin: 0; padding-left: 26px; }
.recipe-ings { list-style: disc; }
.recipe-ings li, .recipe-steps li { margin: 0 0 6px; overflow-wrap: anywhere; }
.recipe-ing-head { list-style: none; margin-left: -26px; padding-top: 8px; font-weight: 700; }
.recipe-steps li { margin-bottom: 12px; }
.recipe-notes { display: flex; flex-direction: column; gap: 10px; }
.recipe-note-item { overflow-wrap: anywhere; }
```

Phone-shell rules (inside the phone-shell markers, after the Shopping phone rules):

```css
  :root:not([data-layout="desktop"]) .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  :root:not([data-layout="desktop"]) .recipe-detail { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  :root:not([data-layout="desktop"]) .recipe-main { font-size: 18px; }
  :root:not([data-layout="desktop"]) .recipe-main h2 { font-size: 26px; }
  :root:not([data-layout="desktop"]) .recipe-sort, :root:not([data-layout="desktop"]) .recipe-chip,
  :root:not([data-layout="desktop"]) .recipe-back { min-height: 44px; }
```

- [ ] **Step 6: Run to verify they pass, then both full suites**

Run: `node --test tests/js/*.mjs` and `PYTHONUTF8=1 PYTHONPATH=src <venv python> -m pytest tests/test_static.py tests/test_js.py -q`
Expected: all pass, including `test_every_referenced_class_is_styled` (every class above has a rule: `recipes`, `overlay-title`, `recipes-bar`, `recipes-search`, `recipes-sorts`, `recipes-chips`, `recipe-sort`, `recipe-chip`, `on`, `recipe-grid`, `recipe-card`, `recipe-thumb`, `recipe-noimg`, `is-broken`, `recipe-name`, `recipe-time`, `recipes-note`, `recipe-back`, `recipe-detail`, `recipe-side`, `recipe-photo`, `recipe-meta`, `recipe-main`, `recipe-desc`, `recipe-ing-head`, `recipe-ings`, `recipe-steps`, `recipe-notes`, `recipe-note-item`). `recipe-side` needs a rule: add `.recipe-side { min-width: 0; }`.

- [ ] **Step 7: Changelog bullet and commit**

```markdown
- Recipes: a native Recipes view (photo grid, search, category chips, four sorts, and a recipe
  page with ingredients, steps and notes) that opens full screen on the wall and the phone.
  Typing never repaints the search box, Back restores your place, and a thumbnail that fails to
  load becomes a placeholder.
```
```bash
git add CHANGELOG.md src/family_hub/web/static tests/js/hub-dom.test.mjs
git commit -m "feat(wall): the Recipes overlay - grid, search, chips, sort and recipe detail"
```

---

### Task 7: Entry points, the iframe's removal, and the guards

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (`renderMeals` header)
- Modify: `tests/js/hub-dom.test.mjs` (replace two old tests)
- Modify: `tests/test_static.py` (new guards)
- Modify: `src/family_hub/config.py` (comment only), `README.md` (config row, Meals bullet)

**Interfaces:**
- Consumes: Task 6's `openOverlay('recipes')`.
- Produces: the Dinner card header shows **Recipes** (`data-overlay="recipes"`) whenever the Meals tile is available; no `meals-full` anywhere.

- [ ] **Step 1: Update the old tests and write the new ones.** In `tests/js/hub-dom.test.mjs`:
  - Replace the test `renderMeals: Full screen only with an http(s) URL to open` (~line 1193) with:

```js
test('renderMeals: the header offers Recipes whenever Meals is available, whatever open_url says', () => {
  for (const url of ['http://mealie.invalid:9000', '', undefined, 5, 'javascript:alert(1)']) {
    const html = mealsHtml({ ...MEALS_WEEK(), open_url: url }).html;
    assert.match(html, /data-overlay="recipes"/, `url ${url}`);
    assert.match(html, /⛶ Recipes/);
    assert.doesNotMatch(html, /meals-full|Full screen/);
  }
});
```
  - The test at ~line 1186-1191 asserting "no dead Full screen button when nothing is available" (`assert.doesNotMatch(r.html, /data-overlay/, ...)`) stays valid; leave it.
  - Replace the test `the full-screen Meals view opens only an http(s) URL the TILE supplied` (~line 1399) with:

```js
test('the Recipes overlay builds the view and never an iframe', () => {
  const { document, sandbox } = newHub();
  const made = [];
  sandbox.makeIframe = (url) => { made.push(url); return document.createElement('div'); };
  sandbox.fetch = async () => ({ ok: true, status: 200, json: async () => ({ available: false }) });
  vm.runInContext(LISTED + "mealsData = { available: true, open_url: 'http://mealie.invalid:9000' };", sandbox);
  sandbox.openOverlay('recipes');
  assert.equal(vm.runInContext('openView', sandbox), 'recipes');
  assert.deepEqual(made, [], 'the Mealie page is never embedded');
  assert.match(document.getElementById('overlay-content').innerHTML, /id="recipes-full"/);
  sandbox.closeOverlay();
  sandbox.openOverlay('meals-full');
  assert.match(document.getElementById('overlay-content').innerHTML, /^$/, 'the old view name opens nothing');
});
```

  Add the new tests below them:

```js
test('the Dinner header Recipes button opens the Recipes overlay (a header tap, wall and phone alike)', () => {
  const { document, sandbox, fire } = newHub();
  vm.runInContext("data_date = '2026-10-01';" + LISTED, sandbox);
  sandbox.fetch = async () => ({ ok: true, status: 200, json: async () => ({ available: false }) });
  sandbox.renderMeals(MEALS_WEEK());
  const btn = document.getElementById('meals-slot').querySelector('.expand');
  assert.ok(btn); assert.equal(btn.dataset.overlay, 'recipes');
  btn.closest = (s) => (s === '.expand' ? btn : null);
  fire('click', { target: btn, preventDefault() {} });
  assert.equal(vm.runInContext('openView', sandbox), 'recipes');
});
```

- [ ] **Step 2: Add the static guards** to `tests/test_static.py`:

```python
def test_recipes_view_is_wired_and_the_mealie_iframe_is_gone():
    hub = (STATIC / "hub.js").read_text(encoding="utf-8")
    assert "view === 'recipes'" in hub and "overlay: 'recipes'" in hub
    assert "meals-full" not in hub, "the Mealie iframe branch is removed"
    assert "makeIframe(url)" not in hub[hub.index("view === 'recipes'"):hub.index("view === 'cameras-page'")], \
        "the Recipes branch never embeds Mealie"
    assert re.search(r'id="recipe-search" class="txt-input', hub), \
        "the search box carries .txt-input, the class the on-screen keyboard serves"
    common = (STATIC / "common.js").read_text(encoding="utf-8")
    assert re.search(r"view === 'recipes'\)\s*return\s+\d{6,}", common), "Recipes gets a long idle timeout"


def test_recipes_css_is_light_enough_for_a_pi_3_and_adapts_to_the_phone():
    rules = re.findall(r"(?m)^[^{}\n/][^{}\n]*\.recipe[^{}]*\{[^}]*\}", CSS)
    assert len(rules) >= 12, "the Recipes view's rules"
    for rule in rules:
        assert "backdrop-filter" not in rule and "animation" not in rule and "transition" not in rule, rule
    mobile = _phone_shell_css()
    assert re.search(r"\.recipe-grid\s*\{[^}]*repeat\(2,", mobile), "two cards across on the phone"
    assert re.search(r"\.recipe-detail\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)", mobile), "one column on the phone"
    assert re.search(r"\.recipe-sort,[^{]*\.recipe-back\s*\{[^}]*min-height:\s*44px", mobile), "44px tap targets"
```

- [ ] **Step 3: Remove the Mealie iframe and change the header** (`hub.js`). Delete the whole `view === 'meals-full'` branch of `openOverlay` (its comment block and the `makeIframe(url)` line). In `renderMeals`, replace the `hasUrl` computation and `head` with:

```js
  const head = sectionHead('Dinner', m && m.available ? { overlay: 'recipes', expandLabel: 'Recipes' } : {});
```
(delete the `const hasUrl = ...` line above it).

- [ ] **Step 4: Docs.** In `README.md`: in the Meals bullet replace "**⛶ Full screen** opens Mealie itself" with a sentence describing the **⛶ Recipes** button (opens the native Recipes view: photo grid, search, category chips, sort by A to Z / recently added / recently made / top rated, and a recipe page with ingredients, steps and notes; read-only); add a short "Recipes" bullet next to the Shopping bullet if the README style lists features separately; in the `mealie` config row change "`open_url` is what **Full screen** opens in the browser (default: `base`), for when the hub reaches Mealie by a different address than your screens do" to say it is still accepted but no longer used by the Dinner button (the Recipes view is native). In `src/family_hub/config.py` update the comment at line ~217 ("what the browser opens full-screen") to "kept for old configs; the Dinner button no longer opens it".

- [ ] **Step 5: Run everything**

Run: `node --test tests/js/*.mjs` and `PYTHONUTF8=1 PYTHONPATH=src <venv python> -m pytest tests/test_static.py tests/test_js.py tests/test_meals.py tests/test_demo.py tests/test_no_house_data.py -q`
Expected: all pass. If `test_every_referenced_class_is_styled` or another existing guard fails because of the removed Full-screen wording, fix the guard to the new rule (the old assertion pinned behaviour this task deliberately changes) and note it in the commit message.

- [ ] **Step 6: Changelog bullet and commit**

```markdown
- Recipes: the Dinner card's **Full screen** button is now **Recipes** and opens the native
  view instead of embedding Mealie (a 15-25 second blank page on a Pi 3). The `open_url`
  setting is still accepted but no longer used.
```
```bash
git add CHANGELOG.md README.md src tests
git commit -m "feat(wall): Dinner header opens Recipes; the Mealie iframe is removed"
```

---

### Task 8: Visual gates, docs, review, PR (the repo's gauntlet)

Needs a real browser. Headless Edge over the DevTools protocol works on the dev PC (see the Shopping card's `shot.mjs` approach); Firefox's headless screenshot fails there.

**Files:**
- Modify: `docs/hub.png`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: Run the demo and look at it.** `DEMO=1 DISABLE_SYNC=1 CONFIG_PATH=config.demo.json DB_PATH=<tmp>/hub.db TOKEN_PATH=<tmp>/token.json PYTHONUTF8=1 PYTHONPATH=src <venv python> -m uvicorn family_hub.app:app --app-dir src --port 8199`. In a browser with a cleared cache check, at full size:
  - Wall at 1920 px: the Dinner header shows **⛶ Recipes**; tap it; the grid fills the screen (about six cards across), the search box, four sort buttons and the category chips are above it; each sort re-orders as the spec says (recently made: never-made last; top rated: unrated last); a chip filters; typing filters and the box keeps focus (on `?kiosk=1`, the on-screen keyboard stays up while typing); a card opens the detail with ingredients (with section headings), numbered steps and notes; Back restores search/sort/chip/scroll.
  - All five themes, night, seasons on and off, the "wells" look; the gear popover over the view; Escape and the home pill close it.
  - Phone at 390 and 360 px: the Meals tab's Dinner header shows Recipes; two cards across; the detail is one column; no horizontal overflow with a long recipe name; 44 px targets.
  - States (edit the demo payload locally, then revert): empty library, 250 recipes (truncated note), a recipe with no times, a very long name, Mealie down (stop the fake) with Try again.
  - Idle: confirm the view stays open past 90 seconds and returns home after 15 minutes (shorten `idleReturnMs('recipes')` locally to check, then revert).
- [ ] **Step 2: Real-wall checks (operator).** On the Pi 3: the grid appears quickly, thumbnails load as you scroll, searching and sorting are instant, a recipe opens in under a second, and `vcgencmd get_throttled` stays `0x0`. Note the time to first paint and the payload size of `/api/mealie/recipes` with the real library (spec open items).
- [ ] **Step 3: README and screenshot.** The Meals bullet and config row were updated in Task 7; add one line about sorting if missing. Regenerate `docs/hub.png` from the demo at 1920 px wide, full page (the Dinner header now reads Recipes).
- [ ] **Step 4: Run both suites under `TZ=UTC`**, and `tests/test_no_house_data.py`.
- [ ] **Step 5: Review gate.** Run the three review agents (`pr-review-toolkit:silent-failure-hunter`, `code-reviewer`, `pr-test-analyzer`) on the branch diff, passing them the Review Focus above; fix every Critical/Important finding with a test that fails first (and mutation-check any guard test that passes immediately).
- [ ] **Step 6: Push the branch and open the PR** against `dapperdodger/family-hub` `main` (never the upstream `drench44` repo), ending the body with the two PR attribution lines.
- [ ] **Step 7: After merge (operator):** wait for the image build, update the `family-hub` app on TrueNAS, reload the Pi kiosk, and confirm the Recipes view on the real wall.

---

## Self-review (run against the spec)

- **Scope:** grid, search, chips, four sorts (Tasks 5-6), detail with notes and Back-restores-state (Task 6), two endpoints + photo size (Tasks 1-4), entry points on wall and phone (Task 7; the Dinner header button is the same element on both, so the phone's Meals tab gets it without a separate button), demo data (Task 4), long idle (Task 5).
- **Out of scope respected:** no writes, no planning, no scaling/nutrition/rating display, no ingredient search, no time sort, no Mealie link.
- **Backend rules:** one capped request (`RECIPES_MAX` 200, `truncated`, `total`), slug validation before any request, 404/422 mapping, per-slug bounded cache, no-items-list is unavailable (Tasks 1-2); image `size` whitelist with fallback and a separate 160-entry thumbnail cache (Task 3, the 16-entry cache could not hold a grid).
- **Spec open items:** `tiny-original.webp` is confirmed (600x600, 88 KB) and handled with a fallback; `image` is treated as a non-empty string; time strings are shown as given; grid breakpoints are `auto-fill minmax(280px, 1fr)` (six across at 1920, two on the phone via the phone shell); payload size and Pi 3 paint are measured in Task 8.
- **Placeholder scan:** none; every code step has its code. The only operator-supplied values are the live checks in Task 8.
- **Type consistency:** `recipes_tile`/`recipe_detail`/`fetch_image(..., size)` (Tasks 1-4), the summary keys `slug,id,name,time,has_image,categories,tags,added,made,rating` (Tasks 1, 4, 5, 6), detail keys `slug,id,name,has_image,servings,prep,cook,total,description,ingredients,steps,notes` (Tasks 2, 4, 6), `data-recipe-open/back/sort/cat/retry` -> `dataset.recipeOpen/...` (Task 6), `recipesState` fields (Task 6) all match.
