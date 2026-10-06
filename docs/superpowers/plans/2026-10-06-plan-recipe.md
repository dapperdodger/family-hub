# Plan a Recipe on a Day Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Plan it" button on a recipe's page lets the family pick a day and put that recipe on the Mealie meal plan as the day's dinner, replacing whatever dinner was there.

**Architecture:** One new write in `meals.py` (`plan_recipe`) reuses the plan read, validation and error mapping of `random_dinner`; one route `POST /api/mealie/plan` under the existing meals write lock; the Recipes detail view gets a button and a row of day chips built from the data the Dinner card already holds.

**Tech Stack:** FastAPI + httpx (Python), vanilla JS, pytest (`FakeMealie` with `MockTransport`), node:test with the fake DOM in `tests/js/hub-dom.test.mjs`.

**Spec:** `docs/superpowers/specs/2026-10-06-plan-recipe-design.md`

## Global Constraints

- A hub pick REPLACES every dinner on that day (hand-planned or hub-rolled); never two dinners from this action.
- The new dinner is NOT put in the re-roll memory (`rolled`), so no Re-roll is offered for it. Removed entries ARE dropped from it.
- Only dates `today <= day < today + mealie.days` (same rule as `random_dinner`); `recipe_id` must pass `valid_uuid`.
- Create the new entry FIRST, delete old dinners after; a failed create leaves the day untouched; a failed delete keeps the new dinner and says so.
- Non-dinner entries (breakfast, lunch) on the day are never touched.
- Token stays on the server; the public repo carries no real IPs or tokens (use `192.168.1.50` in docs; `test_no_house_data` guards this).
- Everything from Mealie is rendered as escaped text. Buttons are real `<button>`s, 44px on the phone.
- New CSS classes must be styled (`test_every_referenced_class_is_styled`); keep comparisons in helper functions, not inside `class="..."` templates.
- Each src commit adds its own NEW "- " bullet under CHANGELOG `## [Unreleased]` (hook); no duplicate `### Added` headings.
- Python tests: run with the scratchpad venv, `TZ=UTC`; 49 Python tests fail identically on clean main on Windows (backup, install_hooks, caldav, google_client, check_changelog, api health) and are not this branch's.

## Review Focus

- The same recipe tapped twice quickly (double tap, two phones): the second call must change nothing.
- A day with several dinners (hand-planned "+N"): all of them are removed, not just the first.
- A lunch/breakfast entry on the target day survives.
- Mealie accepts the create but a delete fails: the day shows the new dinner and the toast says the old one must be removed in Mealie.
- A Mealie that answers the create with junk (no entry id) must not delete anything.
- The re-roll memory keeps no entry that was deleted, and never gains the new one.

---

### Task 1: Probe script for Mealie's create-entry call

**Files:**
- Create: `scripts/probe_mealplan_create.py` is NOT added to the repo; write it in the scratchpad (`probe_mealplan_create.py`) like the shopping probe. Nothing is committed.

**Interfaces:**
- Produces: the confirmed request/response shape the rest of this plan assumes: `POST /api/households/mealplans` with `{"date": "YYYY-MM-DD", "entryType": "dinner", "recipeId": "<uuid>"}` returns an object with an integer `id` and `recipeId`; `DELETE /api/households/mealplans/{id}` removes it.

- [ ] **Step 1: Write the probe**

```python
"""Probe Mealie's meal-plan create call. Run by the operator with their real token:
    PowerShell: $env:MEALIE_API_TOKEN="..."; python probe_mealplan_create.py
Creates ONE throwaway dinner on a date far in the future, reads it back, deletes it."""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("MEALIE_BASE", "http://192.168.1.50:9000")
TOKEN = os.environ["MEALIE_API_TOKEN"]
DAY = "2030-01-01"


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


status, recipes = call("GET", "/api/recipes?perPage=1")
rid = recipes["items"][0]["id"]
print("recipe:", rid)
status, made = call("POST", "/api/households/mealplans", {"date": DAY, "entryType": "dinner", "recipeId": rid})
print("create:", status, json.dumps(made)[:400])
assert status in (200, 201) and isinstance(made, dict) and isinstance(made.get("id"), int), "unexpected create reply"
print("recipeId echoed:", made.get("recipeId") == rid)
status, plan = call("GET", f"/api/households/mealplans?start_date={DAY}&end_date={DAY}&perPage=50")
print("read back:", status, [(e["id"], e["entryType"], (e.get("recipe") or {}).get("name")) for e in plan["items"]])
status, _ = call("DELETE", f"/api/households/mealplans/{made['id']}")
print("delete:", status)
status, plan = call("GET", f"/api/households/mealplans?start_date={DAY}&end_date={DAY}&perPage=50")
print("after delete:", len(plan["items"]), "entries on", DAY)
```

Save it in the scratchpad as `probe_mealplan_create.py`. The default base URL is a placeholder: the operator sets `MEALIE_BASE` to the real address when running it.

- [ ] **Step 2: Hand it to the operator**

Tell the operator to run it (token via `$env:MEALIE_API_TOKEN`, never pasted into chat) and paste the output. Do NOT wait: Tasks 2-6 build on the spec's assumed shape. Record the result in the ledger when it arrives; if the shape differs (status 422, id not an int, `recipeId` not echoed), rule on the smallest change to Task 2's POST body and parsing and ledger it. This must be settled before the PR is opened (Task 7).

- [ ] **Step 3: No commit** (nothing in the repo changed). Ledger: `Task 1: complete (probe written, operator run pending)`.

---

### Task 2: Backend `meals.plan_recipe`

**Files:**
- Modify: `src/family_hub/meals.py` (add `plan_recipe` after `random_dinner`)
- Modify: `tests/test_meals.py` (FakeMealie create handler + tests)
- Modify: `CHANGELOG.md` (new bullet)

**Interfaces:**
- Consumes: `_plan`, `_dinner`, `_is_int`, `valid_uuid`, `parse_date`, `mealie_token`, `_headers`, `_fail`, `_invalidate`, `TIMEOUT`, `log` (all in `meals.py`).
- Produces: `async def plan_recipe(client, cfg, env: dict, recipe_id: object, date_str: object, today: dt.date) -> dict`. Success: `{"ok": True, "entry_id": int | None, "recipe_id": str, "same": bool, "removed": [int, ...]}`. Failure: `{"ok": False, "error": str, "status": int, ["needs_auth": bool], "removed": [int, ...], ["entry_id": int]}`. `removed` lists the dinner entry ids actually deleted (present on every return so the route can clear the re-roll memory even on a partial failure).

- [ ] **Step 1: Extend FakeMealie and write the failing tests**

In `tests/test_meals.py`, in `FakeMealie.__init__` add `self.create_reply = None` (after `self.calls = []`). In `handler`, immediately BEFORE the `/mealplans/random` branch, add:

```python
        if req.method == "POST" and p == "/api/households/mealplans":
            body = json.loads(req.content)
            if self.create_reply is not None:
                return httpx.Response(200, json=self.create_reply)
            self.next_id += 1
            new = entry(self.next_id, body["date"], name=f"Planned {self.next_id}", rid=body["recipeId"])
            self.plan.append(new)
            return httpx.Response(200, json=new)
```

Append these tests after the random/re-roll tests (use a free spot before the `# ---` section for the shopping tests; search for `def test_shopping` to find it):

```python
# ------------------------------------------------------------- plan a recipe on a day

_DEFAULT = object()


def plan_it(fake, date=_DEFAULT, rid=RID2, cfg=None):
    day = d(2) if date is _DEFAULT else date          # None is a real (bad) date the tests pass on purpose
    return run(fake, lambda c, cf: meals.plan_recipe(c, cf, ENV, rid, day, TODAY), cfg)


def dinners_on(fake, day):
    return [e for e in fake.plan if e["date"] == day and e["entryType"] == "dinner"]


def test_plan_an_empty_day_creates_the_dinner_with_exactly_the_documented_body():
    fake = FakeMealie([entry(1, d(0))])
    r = plan_it(fake)
    assert r["ok"] is True and r["same"] is False and r["removed"] == [] and r["recipe_id"] == RID2
    post = [c for c in fake.calls if c["method"] == "POST" and c["path"] == "/api/households/mealplans"]
    assert [c["body"] for c in post] == [{"date": d(2), "entryType": "dinner", "recipeId": RID2}]
    assert [e["recipeId"] for e in dinners_on(fake, d(2))] == [RID2]


def test_plan_replaces_a_hand_planned_dinner_creating_first_then_deleting():
    fake = FakeMealie([entry(7, d(2), name="Hand Planned")])
    r = plan_it(fake)
    assert r["ok"] is True and r["removed"] == [7]
    assert [e["recipeId"] for e in dinners_on(fake, d(2))] == [RID2], "only the new dinner is left"
    methods = [m for m, p in fake.log if p.startswith("/api/households/mealplans") and m in ("POST", "DELETE")]
    assert methods == ["POST", "DELETE"], "created first, removed after"


def test_plan_replaces_every_dinner_on_the_day_but_never_a_lunch_or_another_day():
    fake = FakeMealie([entry(7, d(2)), entry(8, d(2), name="Second"),
                       entry(9, d(2), name="Lunch", entryType="lunch"), entry(10, d(3), name="Other day")])
    r = plan_it(fake)
    assert r["ok"] is True and sorted(r["removed"]) == [7, 8]
    assert [e["id"] for e in fake.plan if e["id"] in (9, 10)] == [9, 10]
    assert [e["recipeId"] for e in dinners_on(fake, d(2))] == [RID2]


def test_plan_the_same_recipe_again_changes_nothing():
    fake = FakeMealie([entry(7, d(2), rid=RID2)])
    r = plan_it(fake)
    assert r == {"ok": True, "entry_id": 7, "recipe_id": RID2, "same": True, "removed": []}
    assert not [1 for m, p in fake.log if m in ("POST", "DELETE")], "no write at all"


def test_plan_the_same_recipe_among_several_dinners_still_leaves_exactly_one():
    fake = FakeMealie([entry(7, d(2), rid=RID2), entry(8, d(2), name="Second")])
    r = plan_it(fake)
    assert r["ok"] is True and r["same"] is False and sorted(r["removed"]) == [7, 8]
    assert len(dinners_on(fake, d(2))) == 1


@pytest.mark.parametrize("date", [d(-1), d(5), d(40), "2026-13-01", "nope", "", None, 5])
def test_plan_rejects_dates_outside_the_planned_days_before_touching_mealie(date):
    fake = FakeMealie([])
    r = plan_it(fake, date=date)
    assert r["ok"] is False and r["status"] == 422 and fake.log == []


@pytest.mark.parametrize("rid", ["nope", "", None, 5, RID2 + "\n", "../../x"])
def test_plan_rejects_a_bad_recipe_id_before_touching_mealie(rid):
    fake = FakeMealie([])
    r = plan_it(fake, rid=rid)
    assert r["ok"] is False and r["status"] == 422 and fake.log == []


def test_plan_needs_meals_configured_and_a_token():
    fake = FakeMealie([])
    off = run(fake, lambda c, cf: meals.plan_recipe(c, Config(), ENV, RID2, d(1), TODAY))
    assert off["ok"] is False and off["status"] == 404
    no_tok = run(fake, lambda c, cf: meals.plan_recipe(c, cf, {}, RID2, d(1), TODAY))
    assert no_tok["ok"] is False and no_tok["status"] == 503 and no_tok["needs_auth"] is True
    assert fake.log == []


def test_plan_a_failed_create_leaves_the_day_untouched():
    fake = FakeMealie([entry(7, d(2))])
    fake.fail[("POST", "/api/households/mealplans")] = 500
    r = plan_it(fake)
    assert r["ok"] is False and r["status"] == 502 and r["removed"] == []
    assert [e["id"] for e in dinners_on(fake, d(2))] == [7]
    assert not [1 for m, p in fake.log if m == "DELETE"]


def test_plan_a_create_reply_without_an_entry_id_deletes_nothing():
    fake = FakeMealie([entry(7, d(2))])
    fake.create_reply = {"recipeId": RID2}
    r = plan_it(fake)
    assert r["ok"] is False and r["status"] == 502
    assert not [1 for m, p in fake.log if m == "DELETE"]


def test_plan_a_failed_delete_keeps_the_new_dinner_and_says_what_to_do():
    fake = FakeMealie([entry(7, d(2)), entry(8, d(2), name="Second")])
    fake.fail[("DELETE", "/api/households/mealplans/7")] = 500
    r = plan_it(fake)
    assert r["ok"] is False and r["status"] == 502 and r["removed"] == [8], "the other one still went"
    assert "remove" in r["error"].lower() and "Mealie" in r["error"]
    assert RID2 in [e["recipeId"] for e in dinners_on(fake, d(2))], "the new dinner stays"


def test_plan_invalidates_the_cached_card_even_when_it_fails():
    fake = FakeMealie([entry(1, d(2), name="Old")])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            cf = mcfg()
            a = await meals.meals_tile(c, cf, ENV, TODAY, {})
            await meals.plan_recipe(c, cf, ENV, RID2, d(2), TODAY)
            b = await meals.meals_tile(c, cf, ENV, TODAY, {})
            return a, b
    a, b = asyncio.run(go())
    assert a["days"][2]["dinner"]["name"] == "Old" and b["days"][2]["dinner"]["name"].startswith("Planned")
```

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC <venv>/python -m pytest tests/test_meals.py -q -k "plan_"`
Expected: FAIL (`AttributeError: module 'family_hub.meals' has no attribute 'plan_recipe'`) on every new test.

- [ ] **Step 3: Implement**

Add after `random_dinner` in `src/family_hub/meals.py`:

```python
async def plan_recipe(client, cfg, env: dict, recipe_id: object, date_str: object,
                      today: dt.date) -> dict:
    """Make ``recipe_id`` the dinner on ``date_str``: it REPLACES every dinner already on that day
    (hand-planned or hub-picked: an explicit pick here is the dinner). The new entry is created
    FIRST so a failure never leaves the day empty; old dinners are removed after. Other meal types
    on the day are never touched. Re-planning the day's only dinner as the same recipe writes
    nothing. Returns ``{ok, entry_id, recipe_id, same, removed}``; ``removed`` lists the dinner ids
    actually deleted (also on failure, so the caller can forget them)."""
    removed: list[int] = []
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"ok": False, "error": "Meals is not configured", "status": 404, "removed": removed}
    if not mealie_token(env):
        return {"ok": False, "error": "MEALIE_API_TOKEN is not set", "status": 503,
                "needs_auth": True, "removed": removed}
    day = parse_date(date_str)
    if day is None or not (today <= day < today + dt.timedelta(days=mc["days"])):
        return {"ok": False, "error": "date is outside the planned days", "status": 422, "removed": removed}
    if not valid_uuid(recipe_id):
        return {"ok": False, "error": "not a recipe id", "status": 422, "removed": removed}
    mealplans = f"{mc['base']}/api/households/mealplans"
    try:
        try:
            plan = await _plan(client, mc, env, day, day)
            existing = [e for e in plan if e.get("entryType") == "dinner"]
            if len(existing) == 1:
                only = _dinner(existing[0])
                if only and only["recipe_id"] == recipe_id:
                    return {"ok": True, "entry_id": only["id"], "recipe_id": recipe_id,
                            "same": True, "removed": removed}
            r = await client.post(mealplans, json={"date": day.isoformat(), "entryType": "dinner",
                                                   "recipeId": recipe_id},
                                  headers=_headers(env), timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            new_id = body.get("id") if isinstance(body, dict) else None
            if not _is_int(new_id):
                raise ValueError("plan reply has no entry id")
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            log.warning("meals plan failed: %s", e)
            return {**_fail(e), "status": 502, "removed": removed}
        failure: BaseException | None = None
        for old in existing:
            old_id = old.get("id")
            if not _is_int(old_id):
                continue
            try:
                d = await client.delete(f"{mealplans}/{old_id}", headers=_headers(env), timeout=TIMEOUT)
                if d.status_code != 404:       # already gone is exactly what we wanted
                    d.raise_for_status()
                removed.append(old_id)
            except httpx.HTTPError as e:
                log.warning("meals plan: removing dinner %s failed: %s", old_id, e)
                failure = failure or e
        if failure is not None:
            err = _fail(failure)
            err["error"] += " -- the new dinner is planned, but an old one could not be removed; remove it in Mealie"
            return {**err, "status": 502, "entry_id": new_id, "removed": removed}
        return {"ok": True, "entry_id": new_id, "recipe_id": recipe_id, "same": False, "removed": removed}
    finally:
        _invalidate()
```

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC <venv>/python -m pytest tests/test_meals.py -q`
Expected: all pass (the new `plan_` tests plus the existing ones).

- [ ] **Step 5: Mutation-check the new tests**

Temporarily (restore each from a backup copy of `meals.py`): (a) delete only the first old dinner (`existing[:1]`), (b) delete before create, (c) drop the `same` early return, (d) drop the `entryType == "dinner"` filter, (e) skip `_invalidate()`. Each must make at least one new test fail. Restore and confirm `cmp` against the backup.

- [ ] **Step 6: Commit**

Add under `## [Unreleased]` → `### Added` a new bullet: `- Planning: a recipe can be made a day's dinner (replacing whatever was planned for that day) through POST /api/mealie/plan; the new dinner is not offered for Re-roll.`

```bash
git add src/family_hub/meals.py tests/test_meals.py CHANGELOG.md
git commit -m "feat: plan_recipe makes a recipe the day's dinner, replacing what was there"
```

---

### Task 3: Route and demo

**Files:**
- Modify: `src/family_hub/app.py` (model + route, after `mealie_random`)
- Modify: `tests/test_api.py` (route tests, next to the other meals route tests or at the end of the meals section)
- Modify: `tests/test_demo.py` (demo reply)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `meals.plan_recipe` (Task 2), `_meals_write_lock`, `_meals_rolled`, `_meals_rolled_save`, `_meals_reply`, `_today`, `DEMO`, `cfg`, `_http`, `log`.
- Produces: `POST /api/mealie/plan` body `{"recipe_id": str, "date": str}`; reply `{ok, entry_id, recipe_id, same, removed}` (demo: `{"ok": true, "demo": true}`); failures are `HTTPException(status, error)` like `/api/mealie/random`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_demo.py` next to the random assertion (around the `/api/mealie/random` demo test):

```python
def test_demo_plan_is_a_no_op_that_says_ok(demo_client):
    r = demo_client.post("/api/mealie/plan", json={"recipe_id": "anything", "date": "2026-10-03"})
    assert r.status_code == 200 and r.json() == {"ok": True, "demo": True}
```

In `tests/test_api.py` (uses `client` and `app_mod`; look at how neighbouring meals tests obtain `app_mod` and follow that):

```python
def test_plan_route_forgets_removed_entries_and_never_remembers_the_new_one(client, app_mod, monkeypatch):
    app_mod._meals_rolled_save({5: ("08481e68-b32a-45db-9f99-f036126dba27", "2026-10-07"), 6: (None, "2026-10-08")})
    async def fake_plan(*a, **k):
        return {"ok": True, "entry_id": 9, "recipe_id": "9cc3dd7f-6004-48f8-b70a-188022e816b9", "same": False, "removed": [5]}
    monkeypatch.setattr(app_mod.meals, "plan_recipe", fake_plan)
    r = client.post("/api/mealie/plan", json={"recipe_id": "9cc3dd7f-6004-48f8-b70a-188022e816b9", "date": "2026-10-07"})
    assert r.status_code == 200 and r.json()["entry_id"] == 9
    assert set(app_mod._meals_rolled()) == {6}, "5 forgotten, 9 never remembered, 6 untouched"


def test_plan_route_forgets_entries_even_when_the_write_half_failed(client, app_mod, monkeypatch):
    app_mod._meals_rolled_save({5: (None, "2026-10-07")})
    async def fake_plan(*a, **k):
        return {"ok": False, "error": "x", "status": 502, "removed": [5]}
    monkeypatch.setattr(app_mod.meals, "plan_recipe", fake_plan)
    r = client.post("/api/mealie/plan", json={"recipe_id": "9cc3dd7f-6004-48f8-b70a-188022e816b9", "date": "2026-10-07"})
    assert r.status_code == 502 and r.json()["detail"] == "x"
    assert app_mod._meals_rolled() == {}


def test_plan_route_rejects_a_body_without_both_fields(client):
    assert client.post("/api/mealie/plan", json={"date": "2026-10-07"}).status_code == 422
    assert client.post("/api/mealie/plan", json={"recipe_id": "x"}).status_code == 422
```

(`_meals_rolled_save` values are `(recipe_or_None, date)`; if `_meals_rolled` drops a `None` recipe shape, use a valid-UUID recipe in the second test as in the first.)

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC <venv>/python -m pytest tests/test_demo.py tests/test_api.py -q -k "plan_route or demo_plan"`
Expected: FAIL with 404/405 (no such route).

- [ ] **Step 3: Implement**

After `MealsRandomIn` add:

```python
class MealsPlanIn(BaseModel):
    recipe_id: str
    date: str
```

After `mealie_random` add:

```python
@app.post("/api/mealie/plan")
async def mealie_plan(body: MealsPlanIn):
    if DEMO:
        return {"ok": True, "demo": True}
    async with _meals_write_lock:
        res = await meals.plan_recipe(_http, cfg, os.environ, body.recipe_id, body.date, _today())
        # dinners removed here are gone whether or not the whole write succeeded: forget them. The new
        # dinner is deliberately NOT remembered as hub-picked, so the card offers no Re-roll for it.
        # Mealie has already changed, so a failed save only leaves a stale entry the card ignores.
        rolled = _meals_rolled()
        gone = [i for i in res.get("removed", []) if i in rolled]
        if gone:
            for i in gone:
                rolled.pop(i, None)
            try:
                _meals_rolled_save(rolled)
            except Exception:
                log.exception("meals: could not save the re-roll memory (the plan itself went through)")
    return _meals_reply(res)
```

`_meals_reply` must run after the memory is saved; it only reads `res`, so returning after the `async with` is fine and keeps the lock short.

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC <venv>/python -m pytest tests/test_demo.py tests/test_api.py tests/test_meals.py -q -k "plan or meals or mealie"`
Expected: pass; then the full run shows only the 49 known Windows failures.

- [ ] **Step 5: Commit**

CHANGELOG new bullet under Added: `- Planning: the demo hub answers the new plan route with a harmless ok, like the other meal writes.`

```bash
git add src/family_hub/app.py tests/test_api.py tests/test_demo.py CHANGELOG.md
git commit -m "feat: POST /api/mealie/plan route, re-roll memory cleared for removed dinners"
```

---

### Task 4: The Plan it button and day chips

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (Recipes block: state, `recipePlanHtml`, `recipeDetailHtml`, click handlers, `planRecipe`)
- Modify: `tests/js/hub-dom.test.mjs` (tests after the existing Recipes tests)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `recipesState` (`slug`, `detail`), `mealsData` (`{available, days: [{date, dinner: {name} | null}]}`), `data_date`, `todayISO()`, `mealsDayLabel(date, todayStr)` (returns "Tonight"/"Tomorrow"/weekday name), `escapeHtml`, `j`, `JSON_POST`, `showToast`, `fetchMeals()`, `renderRecipes()`, `recipesHost()`.
- Produces: `recipesState.planOpen: boolean`, `recipesState.planBusy: boolean`; `function planDays(): Array<{date, label, now}>` (empty array when `mealsData` has no usable days); `async function planRecipe(date)`; click targets `[data-recipe-plan]` (toggle the chips) and `[data-recipe-plan-day]` (carries the date). Chip markup: `<button type="button" class="recipe-day" data-recipe-plan-day="DATE"[ disabled]><span class="recipe-day-name">LABEL</span><span class="recipe-day-now">NOW</span></button>`.

Toast/behaviour contract: success toast `Planned <recipe name> for <label lowercased unless a weekday>`; use `Planned ${name} for ${label}` with the label exactly as the chip shows it ("Tonight", "Tomorrow", "Wednesday"). Failure toast: the server's message if the error has one, else `That did not work`. Success closes the chips and calls `fetchMeals()`; failure leaves the chips open. `planBusy` blocks a second submit and disables the chips. `recipesReset()` and `recipesBack()` clear both flags.

- [ ] **Step 1: Write the failing tests**

Add to `hub-dom.test.mjs` after the last Recipes test. Use the existing helpers (`rcpOpen`, `rcpFetch`, `tapRcp`, `rcpHtml`, `MEALS_WEEK`, `flush`). Seed `mealsData` with `vm.runInContext("mealsData = ...", sandbox)` and set `data_date` so the labels are deterministic (look at how the Meals tests do it: `"data_date = '2026-10-01';" + LISTED`).

```javascript
async function rcpPlanOpen(opts = {}) {
  const r = await rcpOpen(opts);
  vm.runInContext("data_date = '2026-10-01';", r.sandbox);
  r.sandbox.mealsData = undefined;
  vm.runInContext(`mealsData = ${JSON.stringify(opts.meals || MEALS_WEEK())};`, r.sandbox);
  tapRcp(r.fire, r.host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  return r;
}

test('Recipes: a recipe page offers Plan it; the chips list the shown days with what is planned', async () => {
  const r = await rcpPlanOpen();
  assert.match(rcpHtml(r.host), /data-recipe-plan[ >]/);
  assert.doesNotMatch(rcpHtml(r.host), /data-recipe-plan-day/, 'closed until asked');
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  const html = rcpHtml(r.host);
  const days = vm.runInContext('planDays()', r.sandbox);
  assert.equal(Array.from(days).length, vm.runInContext('mealsData.days.length', r.sandbox));
  assert.match(html, /class="recipe-day-name">Tonight</);
  assert.match(html, /class="recipe-day-name">Tomorrow</);
  assert.match(html, /class="recipe-day-now">/);
  assert.match(html, /Nothing planned/, 'an empty day says so');
});

test('Recipes: no Meals days loaded means no Plan it button at all', async () => {
  const r = await rcpPlanOpen({ meals: { available: false } });
  assert.doesNotMatch(rcpHtml(r.host), /data-recipe-plan/);
});

test('Recipes: tapping a day plans the recipe, toasts, closes the chips and refreshes the Dinner card', async () => {
  const r = await rcpPlanOpen();
  const posts = [];
  const seen = [];
  const base = r.sandbox.fetch;
  r.sandbox.fetch = async (url, o) => {
    seen.push(url);
    if (url === '/api/mealie/plan') { posts.push(JSON.parse(o.body)); return { ok: true, status: 200, json: async () => ({ ok: true }) }; }
    return base(url, o);
  };
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  const day = r.host.querySelector('[data-recipe-plan-day]');
  const date = day.dataset.recipePlanDay;
  tapRcp(r.fire, r.host, '[data-recipe-plan-day]', 'data-recipe-plan-day');
  await flush(); await flush();
  assert.deepEqual(posts, [{ recipe_id: RID_A, date }]);
  assert.match(r.document.getElementById('toast').textContent, /^Planned Baked Ziti for /);
  assert.doesNotMatch(rcpHtml(r.host), /data-recipe-plan-day/, 'the chips close');
  assert.ok(seen.includes('/api/tiles/mealie'), 'the Dinner card was re-read');
});

test('Recipes: a failed plan shows the server message and keeps the chips open', async () => {
  const r = await rcpPlanOpen();
  const base = r.sandbox.fetch;
  r.sandbox.fetch = async (url, o) => (url === '/api/mealie/plan'
    ? { ok: false, status: 502, json: async () => ({ detail: 'Mealie said no' }) } : base(url, o));
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  tapRcp(r.fire, r.host, '[data-recipe-plan-day]', 'data-recipe-plan-day');
  await flush(); await flush();
  assert.equal(r.document.getElementById('toast').textContent, 'Mealie said no');
  assert.match(rcpHtml(r.host), /data-recipe-plan-day/);
});

test('Recipes: while a plan is in flight a second tap does nothing and the chips are disabled', async () => {
  const r = await rcpPlanOpen();
  const slow = {}; slow.p = new Promise((res) => { slow.go = res; });
  let posts = 0;
  const base = r.sandbox.fetch;
  r.sandbox.fetch = async (url, o) => {
    if (url === '/api/mealie/plan') { posts += 1; await slow.p; return { ok: true, status: 200, json: async () => ({ ok: true }) }; }
    return base(url, o);
  };
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  tapRcp(r.fire, r.host, '[data-recipe-plan-day]', 'data-recipe-plan-day');
  tapRcp(r.fire, r.host, '[data-recipe-plan-day]', 'data-recipe-plan-day');
  await flush();
  assert.equal(posts, 1);
  assert.match(rcpHtml(r.host), /data-recipe-plan-day="[^"]+" disabled/);
  slow.go(); await flush(); await flush();
});

test('Recipes: Back and reopening clear the Plan it chips', async () => {
  const r = await rcpPlanOpen();
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  tapRcp(r.fire, r.host, '[data-recipe-back]', 'data-recipe-back');
  assert.equal(vm.runInContext('recipesState.planOpen', r.sandbox), false);
  tapRcp(r.fire, r.host, '.recipe-card', 'data-recipe-open');
  await flush(); await flush();
  assert.doesNotMatch(rcpHtml(r.host), /data-recipe-plan-day/);
});

test('Recipes: a dinner name from Mealie in a chip is inert text', async () => {
  const evil = '<img src=x onerror=alert(1)>';
  const meals = MEALS_WEEK();
  meals.days[0].dinner = { id: 1, recipe_id: RID_A, name: evil, description: '', has_image: false, rolled: false, more: 0 };
  const r = await rcpPlanOpen({ meals });
  tapRcp(r.fire, r.host, '[data-recipe-plan]', 'data-recipe-plan');
  assert.doesNotMatch(rcpHtml(r.host), /<img src=x/);
  assert.match(rcpHtml(r.host), /&lt;img src=x onerror=alert\(1\)&gt;/);
});
```

The hub-dom `rcpFetch` returns `{}` for unknown URLs such as `/api/tiles/mealie`, which `fetchMeals` tolerates.

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC node --test --test-name-pattern="Recipes" tests/js/hub-dom.test.mjs`
Expected: the new tests FAIL (no `data-recipe-plan`, no `planDays`).

- [ ] **Step 3: Implement**

In `hub.js`, extend the state in the Recipes block: add `planOpen: false, planBusy: false,` to `recipesState`, and in `recipesReset()` the same two keys in the `Object.assign`. In `recipesBack()` add `recipesState.planOpen = false; recipesState.planBusy = false;`. In `openRecipe()` set the same two to false next to `recipesState.detail = null;`.

Add before `recipeDetailHtml`:

```javascript
// The days the Dinner card shows, as chips for "Plan it". Empty when the card has no usable days
// (Meals not loaded or unavailable): the button is then not offered rather than guessing days.
function planDays() {
  const md = mealsData;
  if (!md || !md.available || !Array.isArray(md.days)) return [];
  const today = data_date || todayISO();
  return md.days.filter((d) => d && typeof d.date === 'string').map((d) => ({
    date: d.date,
    label: mealsDayLabel(d.date, today),
    now: d.dinner && d.dinner.name ? String(d.dinner.name) : 'Nothing planned',
  }));
}

function recipePlanHtml() {
  const days = planDays();
  if (!days.length) return '';
  const button = `<button type="button" class="recipe-plan" data-recipe-plan>🗓 Plan it</button>`;
  if (!recipesState.planOpen) return `<div class="recipe-planbox">${button}</div>`;
  const off = recipesState.planBusy ? ' disabled' : '';
  const chips = days.map((d) => `<button type="button" class="recipe-day" data-recipe-plan-day="${escapeHtml(d.date)}"${off}>`
    + `<span class="recipe-day-name">${escapeHtml(d.label)}</span>`
    + `<span class="recipe-day-now">${escapeHtml(d.now)}</span></button>`).join('');
  return `<div class="recipe-planbox">${button}<div class="recipe-days">${chips}</div></div>`;
}

async function planRecipe(date) {
  const d = recipesState.detail;
  if (!d || recipesState.planBusy) return;
  const days = planDays();
  const day = days.find((x) => x.date === date);
  recipesState.planBusy = true;
  renderRecipes();
  try {
    await j('/api/mealie/plan', JSON_POST({ recipe_id: d.id, date }));
    showToast(`Planned ${d.name} for ${day ? day.label : date}`);
    recipesState.planOpen = false;
    fetchMeals();               // the Dinner card behind this view shows the new dinner now
  } catch (e) {
    showToast((e && e.message) ? e.message : 'That did not work');
  } finally {
    recipesState.planBusy = false;
    if (recipesState.slug && recipesState.detail === d) renderRecipes();
  }
}
```

In `recipeDetailHtml`, put the plan box right after the back button's container: change the return so the side column is `<div class="recipe-side">${photo}${recipePlanHtml()}${meta ? ... : ''}</div>`.

Click handlers (next to the other `rc*` handlers in the document click listener):

```javascript
  const rcPlan = e.target.closest('[data-recipe-plan]');
  if (rcPlan) { recipesState.planOpen = !recipesState.planOpen; renderRecipes(); return; }
  const rcPlanDay = e.target.closest('[data-recipe-plan-day]');
  if (rcPlanDay) { planRecipe(rcPlanDay.dataset.recipePlanDay); return; }
```

Place `rcPlanDay` BEFORE `rcPlan` is NOT needed (different attributes), but both must come before the generic fallthrough handlers.

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC node --test --test-name-pattern="Recipes" tests/js/hub-dom.test.mjs` then `TZ=UTC node --test tests/js/*.test.mjs`
Expected: all pass.

- [ ] **Step 5: Mutation-check**

(a) drop the `planBusy` guard, (b) always close chips even on failure, (c) post `d.slug` instead of `d.id`, (d) skip `escapeHtml` on `d.now`, (e) don't clear `planOpen` in `recipesBack`. Each must fail a test; restore from backup.

- [ ] **Step 6: Commit**

CHANGELOG new bullet: `- Recipes: a recipe page has a Plan it button; pick a day and the recipe becomes that day's dinner, replacing what was planned, with no Re-roll.`

```bash
git add src/family_hub/web/static/hub.js tests/js/hub-dom.test.mjs CHANGELOG.md
git commit -m "feat: Plan it on a recipe page, day chips, replace the day's dinner"
```

---

### Task 5: Styling, phone, guards

**Files:**
- Modify: `src/family_hub/web/static/styles.css` (after the Recipes detail rules; phone rules in the phone shell block next to the existing `.recipe-*` phone rules)
- Modify: `tests/test_static.py` (extend `test_recipes_css_is_light_enough_for_a_pi_3_and_adapts_to_the_phone`)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: classes from Task 4: `recipe-planbox`, `recipe-plan`, `recipe-days`, `recipe-day`, `recipe-day-name`, `recipe-day-now`.
- Produces: styled classes (the class guard requires a rule for each).

- [ ] **Step 1: Write the failing guard**

Append to the end of `test_recipes_css_is_light_enough_for_a_pi_3_and_adapts_to_the_phone`:

```python
    for cls in ("recipe-planbox", "recipe-plan", "recipe-days", "recipe-day", "recipe-day-name", "recipe-day-now"):
        assert re.search(rf"\.{cls}\b[^{{]*\{{", CSS), f"{cls} is styled"
    assert re.search(r"\.recipe-day\[disabled\]|\.recipe-day:disabled", CSS), "a busy chip looks inactive"
    assert re.search(r"\.recipe-plan[^{]*\.recipe-day[^{]*\{[^}]*min-height:\s*44px|\.recipe-day,[^{]*\{[^}]*min-height:\s*44px", mobile), \
        "44px plan buttons on the phone"
```

- [ ] **Step 2: Run to verify RED**

Run: `TZ=UTC <venv>/python -m pytest tests/test_static.py -q -k "recipes_css or every_referenced_class"`
Expected: FAIL (classes unstyled).

- [ ] **Step 3: Implement**

After `.recipe-desc {...}` add (no transitions, animations or backdrop-filter; the rules guard forbids them):

```css
.recipe-planbox { margin: 14px 0 0; display: flex; flex-direction: column; gap: 10px; }
.recipe-plan { align-self: flex-start; font: inherit; font-size: 15px; font-weight: 600; color: var(--accent); cursor: pointer;
  background: var(--accent-soft); border: 1px solid var(--accent); border-radius: 999px; padding: 10px 18px; min-height: 44px; }
.recipe-days { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.recipe-day { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-width: 0; text-align: left;
  font: inherit; color: var(--ink); cursor: pointer; background: var(--surface-2); border: 1px solid var(--edge);
  border-radius: 12px; padding: 10px 12px; min-height: 44px; }
.recipe-day[disabled] { opacity: .5; cursor: default; }
.recipe-day-name { font-size: 15px; font-weight: 700; }
.recipe-day-now { font-size: 13px; color: var(--dim); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recipe-plan:focus-visible, .recipe-day:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

In the phone block, extend the existing 44px rule's selector list: `.recipe-sort, .recipe-chip, .recipe-back` becomes `.recipe-sort, .recipe-chip, .recipe-back, .recipe-plan, .recipe-day`, keeping the `:root:not([data-layout="desktop"])` prefix on each selector, and add `:root:not([data-layout="desktop"]) .recipe-days { grid-template-columns: repeat(2, minmax(0, 1fr)); }`. Update the guard regexp if the selector list order differs from what you wrote.

- [ ] **Step 4: Run to verify GREEN**

Run: `TZ=UTC <venv>/python -m pytest tests/test_static.py -q`
Expected: pass (including `test_every_referenced_class_is_styled`).

- [ ] **Step 5: Commit**

CHANGELOG new bullet: `- Recipes: the Plan it day chips are two across on a phone with 44px tap targets.`

```bash
git add src/family_hub/web/static/styles.css tests/test_static.py CHANGELOG.md
git commit -m "style: Plan it button and day chips, phone sizes"
```

---

### Task 6: Docs, visual gates, whole-suite run

**Files:**
- Modify: `README.md` (Recipes bullet: mention Plan it), `docs/hub.png` only if the Dinner card or overlay view changes (it does not), `src/family_hub/demo.py` (none: the demo already has days and recipes)
- Modify: `CHANGELOG.md`
- Modify (deploy repo): `C:\Users\mrtim\Documents\family-hub-deploy\TODO.md` (item 3 done pending real-Mealie verification)

- [ ] **Step 1: README and visual gates**

Edit the Recipes bullet in `README.md` to add: "A recipe page's Plan it button puts that recipe on a chosen day's dinner, replacing whatever was planned there (no Re-roll for it)." Start the demo (`DEMO=1`, scratchpad venv; the same harness as the Recipes gates with `shot.mjs`), open a recipe, tap Plan it, and screenshot: wall (grey/light/black themes), phone width, chips open and busy. Confirm no horizontal overflow, chips readable, the day with a long dinner name ellipsizes.

- [ ] **Step 2: Full suites**

Run `TZ=UTC node --test tests/js/*.test.mjs` (expect all pass) and the full pytest (expect only the 49 known Windows failures; compare the failing set to clean main by file counts).

- [ ] **Step 3: Commit**

CHANGELOG bullet: `- Docs: the README describes Plan it.`

```bash
git add README.md CHANGELOG.md
git commit -m "docs: README describes Plan it"
```

- [ ] **Step 4: Ledger the not-verified items**

Ledger: real Mealie create shape (Task 1 probe output), real wall tap on the Pi, real phone.

---

### Task 7: Review gate, probe result, PR

- [ ] **Step 1:** Run the three review passes the repo asks for (`docs/adding-a-feature.md`): code review of the whole branch with this plan's Review Focus verbatim; apply Critical/Important in ONE fix pass (each fix RED then GREEN, suite green), ledger minors.
- [ ] **Step 2:** The operator's Task 1 probe output must be in the ledger and match the plan's assumed shape. If it is not yet, ask for it now; do not open the PR without it.
- [ ] **Step 3:** Push `feat/plan-recipe` and open the PR with `gh pr create -R dapperdodger/family-hub --base main --head feat/plan-recipe` (plain `gh pr create` resolves to the wrong owner). PR body ends with the attribution line from the session reminder.
- [ ] **Step 4:** In the deploy repo update `TODO.md` item 3 to "built, awaiting merge + real-wall check" and commit there (push only when asked).
