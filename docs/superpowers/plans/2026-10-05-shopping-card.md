# Shopping card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native "Shopping" card (wall, left column beside the To-Do card) and a Shopping section on the phone's Meals tab that shows the Mealie shopping list, lets someone check items off and un-check them, quick-add a free-text item, and delete an item, with the list scrolling inside its card like the meal plan.

**Architecture:** Four new endpoints on the existing Mealie proxy in `meals.py`/`app.py` (read the configured list with its items; add, check/un-check, delete an item), all fail-soft, token-on-server, list-membership-checked. A new `#shopping-slot` in `index.html`'s `.col-left`, painted by `renderShopping` in `hub.js` with the Meals card's patterns (newest-wins fetch, inline row menu, scroll/focus carry across repaints, busy keys). It rides the `mealie` integration's on/off; the To-Do feature is untouched and can be switched off with its existing toggle to give the card the room.

**Tech Stack:** Python 3.13 / FastAPI / httpx / pytest (backend); vanilla JS in `hub.js` with the repo's fake-DOM `node --test` suite; plain CSS in `styles.css`.

**Spec:** `docs/superpowers/specs/2026-10-05-shopping-card-design.md`

## Global Constraints

- Public repo: no real LAN IPs, tokens, calendar ids or house data in code, tests, docs or fixtures. Use `http://mealie` / `192.168.1.50` style placeholders only.
- `MEALIE_API_TOKEN` is read only from the environment (`integrations.mealie_token(env)`); it never reaches the browser or a log line.
- Every Mealie read fails soft (returns `{"available": False}`, never raises); every write returns `{"ok": bool, "error"?, "status"?}` and never raises. The routes have no global handler.
- Every id that goes into an upstream URL path is validated with `meals.valid_uuid` before any request.
- No new env var, no new integration id, no new `/health/full` source (it rides `mealie` / the `meals` source). A failing shopping read must NOT mark the dinner tile red (`tiles.SOURCE_STATE["meals"]` is only touched for the shared `auth_rejected` flag).
- The wall is a fixed 1920 px layout; the phone shell is `@media (max-width: 1000px)` keyed by `:root:not([data-layout="desktop"])`. Tap targets >= 44 px on the phone; nothing `position: fixed`/`sticky` with `backdrop-filter`; no `transform` on fixed interactive elements (CLAUDE.md iOS traps).
- No new animation (nothing to add to the reduced-motion roster); the check mark must NOT reuse `check-pop`.
- Run Python tests with `PYTHONPATH=src python -m pytest ... -p no:anyio` on the dev PC (the `-p no:anyio` avoids a plugin crash in that Windows install; CI does not need it). Install deps once with `python -m pip install -r requirements.txt`. Run JS tests with `node --test tests/js/*.mjs`. Run both under `TZ=UTC` before the PR.
- Every commit that touches `src/**` needs the `CHANGELOG.md` `## [Unreleased]` entry (a pre-commit hook enforces it): Task 3 adds the entry; later tasks append to it.
- Work on branch `feat/shopping-card` (already created from `origin/main`). Commit messages end with the two attribution lines the session was given.

## Review Focus

Failure modes the spec implies that no happy-path test exercises; each is pinned by a test in the task that owns the code:

1. **An item that Mealie has deleted or moved to another list** while the card is on screen: check/delete must be a clean 404, not a blind write, and the card must re-read and drop the phantom row (Task 2 `test_check_an_item_from_another_list_*`, Task 5 rollback test).
2. **Hostile, blank or huge item text:** markup in an item name or in a quick add must render inert; whitespace-only adds post nothing; text over 120 characters is refused; emoji and non-ASCII survive (Task 1 trimming, Task 2 add validation, Task 4 XSS test).
3. **A giant list** (hundreds of items): the read is capped, the open count is still the true count, and the scroller (not the page) takes the overflow (Task 1 cap test, Task 6 scroll guard).
4. **Double taps and concurrent edits:** a second tap on a check or Add while one is in flight sends no second request; two writes never interleave a read-modify-write (Task 3 lock, Task 5 busy tests).
5. **Mealie down or the token rejected mid-session:** the card keeps its last list through transient failures, shows the needs-token note only when the server says so, and a failed write surfaces the server's reason without leaving the row in the wrong state (Task 1 auth/transport tests, Task 5 failure tests).

---

## File Structure

- Modify `src/family_hub/meals.py`: shopping read + three writes + their shared helpers/constants (the module already owns every Mealie call; it grows by about 150 lines, and the new functions are one self-contained block at the end, before `fetch_image`).
- Modify `src/family_hub/app.py`: four routes + models + one write lock, next to the existing `/api/mealie/shopping` POST.
- Modify `src/family_hub/demo.py`: `demo_shopping()`.
- Modify `src/family_hub/web/static/index.html`: the `#shopping-slot` section.
- Modify `src/family_hub/web/static/hub.js`: state, render, fetch, actions, wiring.
- Modify `src/family_hub/web/static/styles.css`: card, scroller, row/menu styles, hide hooks, wells, phone shell.
- Modify tests: `tests/test_meals.py`, `tests/test_demo.py`, `tests/test_static.py`, `tests/js/hub-dom.test.mjs`.
- Modify docs: `CHANGELOG.md`, `README.md`, `docs/hub.png`.
- Separate repo (`family-hub-deploy`): `pi-kiosk/setup-kiosk.sh` + `pi-kiosk/README.md` (Task 8).

---

### Task 0: Environment and live Mealie pre-flight

Settles the one question a fake cannot: what body Mealie's `PUT /api/households/shopping/items/{id}` accepts and preserves for a note item and for a recipe-derived item. The result decides whether Task 2's allowlist stands. This needs the real API token, which only the operator has, so the operator runs it and pastes the output (never the token).

**Files:**
- Create (scratch, not committed): `<scratchpad>/probe_mealie_shopping.py`

- [ ] **Step 1: Install dependencies and confirm the baseline is green**

```bash
cd C:/Users/mrtim/Documents/family-hub
python -m pip install -r requirements.txt
PYTHONPATH=src python -m pytest tests/test_meals.py tests/test_demo.py -q -p no:anyio
node --test tests/js/hub-dom.test.mjs
```
Expected: all pass (JS: `# pass 546`, `# fail 0` at time of writing). If Python fails to import a module, install what it names and rerun. Do not proceed until the baseline is green.

- [ ] **Step 2: Write the probe script**

```python
"""Probe Mealie's shopping-item API. Run by the operator with their real token:
    MEALIE_API_TOKEN=... python probe_mealie_shopping.py
Creates one throwaway note item, checks/unchecks it through the SAME body the hub
will send, then deletes it. If the list has a recipe-derived item (one with a
foodId), it also checks and unchecks that one and reports what changed."""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("MEALIE_BASE", "http://192.168.1.50:9000")
TOKEN = os.environ["MEALIE_API_TOKEN"]
KEEP = ("note", "quantity", "position", "foodId", "unitId", "labelId", "extras")


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


def flip(item, list_id, checked):
    body = {k: item[k] for k in KEEP if k in item}
    body.update({"shoppingListId": list_id, "checked": checked})
    return body


status, lists = call("GET", "/api/households/shopping/lists?perPage=50")
lst = lists["items"][0]
print("list:", lst["name"], "| lists:", len(lists["items"]))
status, full = call("GET", f"/api/households/shopping/lists/{lst['id']}")
items = full["listItems"]
print("GET list ->", status, "| items:", len(items))
for it in items[:3]:
    print("  sample:", {k: it.get(k) for k in ("display", "note", "checked", "position", "quantity", "foodId", "unitId")})

status, made = call("POST", "/api/households/shopping/items",
                    {"shoppingListId": lst["id"], "note": "zz hub probe", "quantity": 1, "checked": False})
print("POST item ->", status)
new = made["createdItems"][0]
print("  created:", {k: new.get(k) for k in ("id", "display", "note", "checked")})
status, got = call("GET", f"/api/households/shopping/items/{new['id']}")
print("GET item ->", status, "| listId matches:", got["shoppingListId"] == lst["id"])
status, _ = call("PUT", f"/api/households/shopping/items/{new['id']}", flip(got, lst["id"], True))
status2, after = call("GET", f"/api/households/shopping/items/{new['id']}")
print("PUT check ->", status, "| now checked:", after["checked"], "| note kept:", after["note"] == got["note"])
status, _ = call("PUT", f"/api/households/shopping/items/{new['id']}", flip(after, lst["id"], False))
print("PUT uncheck ->", status)
print("DELETE ->", call("DELETE", f"/api/households/shopping/items/{new['id']}")[0])

food = next((i for i in items if i.get("foodId") and not i.get("checked")), None)
if food:
    before = {k: food.get(k) for k in ("display", "quantity", "foodId", "unitId", "labelId")}
    s1, _ = call("PUT", f"/api/households/shopping/items/{food['id']}", flip(food, lst["id"], True))
    s2, mid = call("GET", f"/api/households/shopping/items/{food['id']}")
    mid_view = {k: mid.get(k) for k in before}
    s3, _ = call("PUT", f"/api/households/shopping/items/{food['id']}", flip(mid, lst["id"], False))
    s4, end = call("GET", f"/api/households/shopping/items/{food['id']}")
    print("recipe-derived item:", before)
    print("  PUT check ->", s1, "| fields unchanged:", mid_view == before, "| checked:", mid["checked"])
    print("  PUT uncheck ->", s3, "| restored:", end["checked"] is False,
          "| recipeReferences before/after:", len(food.get("recipeReferences") or []), "/", len(end.get("recipeReferences") or []))
else:
    print("no unchecked recipe-derived item on the list; skipped that half")
```

- [ ] **Step 3: Operator runs it and the output decides**

The operator runs it (their token in the environment, never typed into chat) and pastes the output. Pass criteria, all must hold:
- `GET list` returns the items with `display`/`note`/`checked`/`position`; a note item has a usable `display` or `note`.
- `PUT check` -> 200 and the item is `checked: True` with `note` kept.
- For the recipe-derived item: `PUT check` -> 200, `fields unchanged: True`, and `restored: True` after the uncheck.

If `recipeReferences` shrinks from N to 0, that is accepted (only Mealie's own "remove this recipe's ingredients" link is lost; it does not change what the card shows) and is recorded in the CHANGELOG as a known limit in Task 8. If any PUT is not 200, or fields change, STOP and revise Task 2's `_ITEM_KEEP` / body before writing it.

- [ ] **Step 4: Commit nothing.** This task changes no tracked file. Record the pass/fail line for each criterion in the PR description later.

---

### Task 1: Shopping read (`meals.shopping_tile`)

**Files:**
- Modify: `src/family_hub/meals.py` (constants after line ~48, `reset_caches`/`forget_plan` at lines ~62-70, new block before `fetch_image`)
- Test: `tests/test_meals.py` (extend `FakeMealie`, add fixtures and tests)

**Interfaces:**
- Consumes: existing `_shopping_list(client, mc, env) -> (list_id, list_name)`, `_headers`, `valid_uuid`, `_is_int`, `_auth_failed`, `_note_auth`, `tiles._note_error`, `TIMEOUT`.
- Produces: `async def shopping_tile(client, cfg, env) -> dict` returning `{"available": False}` | `{"available": False, "needs_auth": True}` | `{"available": True, "list": {"id", "name"}, "items": [{"id", "text", "checked"}], "open": int}`; `def _invalidate_shopping() -> None`; module state `_shop_cache`, `_shop_gen`; constants `SHOPPING_TTL = 10.0`, `SHOPPING_MAX_ITEMS = 200`, `ITEM_TEXT_MAX = 120`.

- [ ] **Step 1: Extend the test fake and add fixtures** (top of `tests/test_meals.py`, after `RID2`)

```python
IID1 = "11111111-1111-4111-8111-111111111111"
IID2 = "22222222-2222-4222-8222-222222222222"
IID3 = "33333333-3333-4333-8333-333333333333"
OTHER_LIST = "99999999-9999-4999-8999-999999999999"


def item(iid, text, checked=False, position=0, list_id=RID2, **kw):
    """A shopping-list item as Mealie returns it."""
    it = {"id": iid, "shoppingListId": list_id, "display": text, "note": text,
          "checked": checked, "position": position, "quantity": 1,
          "foodId": None, "unitId": None, "labelId": None, "extras": {}}
    it.update(kw)
    return it
```

Change `FakeMealie.__init__` to accept items and add the handlers (insert the new branches just before the final `return httpx.Response(404)` of `handler`):

```python
    def __init__(self, plan=None, lists=None, items=None):
        self.plan = list(plan or [])
        self.lists = lists if lists is not None else [{"id": RID2, "name": "Groceries"}]
        self.items = list(items or [])
        self.log = []
        ...  # (the rest of __init__ is unchanged)
```

```python
        if req.method == "GET" and p == f"/api/households/shopping/lists/{RID2}":
            return httpx.Response(200, json={"id": RID2, "name": "Groceries", "listItems": self.items})
        if req.method == "POST" and p == "/api/households/shopping/items":
            body = json.loads(req.content)
            self.next_id += 1
            new = item(f"{self.next_id:08d}-0000-4000-8000-000000000000", body["note"],
                       position=len(self.items), list_id=body["shoppingListId"])
            self.items.append(new)
            return httpx.Response(201, json={"createdItems": [new]})
        if p.startswith("/api/households/shopping/items/"):
            found = next((i for i in self.items if i["id"] == p.rsplit("/", 1)[1]), None)
            if found is None:
                return httpx.Response(404, json={"detail": "not found"})
            if req.method == "GET":
                return httpx.Response(200, json=found)
            if req.method == "PUT":
                found.update(json.loads(req.content))
                return httpx.Response(200, json={"updatedItems": [found]})
            if req.method == "DELETE":
                self.items = [i for i in self.items if i is not found]
                return httpx.Response(200, json={})
```

- [ ] **Step 2: Write the failing read tests** (append a new section `# ---- shopping read` to `tests/test_meals.py`)

```python
# ------------------------------------------------------------- shopping read

def shop(fake, cfg=None):
    return run(fake, lambda c, cfg_: meals.shopping_tile(c, cfg_, ENV), cfg)


def test_shopping_read_shape_orders_unchecked_first_and_counts_open():
    fake = FakeMealie(items=[
        item(IID1, "Eggs", checked=True, position=0),
        item(IID2, "Milk", position=2),
        item(IID3, "Bread", position=1),
    ])
    out = shop(fake)
    assert out == {"available": True, "list": {"id": RID2, "name": "Groceries"}, "open": 2,
                   "items": [{"id": IID3, "text": "Bread", "checked": False},
                             {"id": IID2, "text": "Milk", "checked": False},
                             {"id": IID1, "text": "Eggs", "checked": True}]}


def test_shopping_read_prefers_display_then_note_and_skips_unusable_items():
    fake = FakeMealie(items=[
        item(IID1, "2 cups flour", note=""),                      # recipe-derived: display only
        item(IID2, "", display="", note="Paper towels"),          # note only
        {"id": "not-a-uuid", "display": "x", "checked": False},   # bad id
        item(IID3, "   ", display="   ", note=None),              # nothing to show
        "junk", None, 5,
    ])
    out = shop(fake)
    assert [i["text"] for i in out["items"]] == ["2 cups flour", "Paper towels"]


def test_shopping_read_collapses_whitespace_and_trims_long_text():
    fake = FakeMealie(items=[item(IID1, "  a \n  b  " + "x" * 300)])
    text = shop(fake)["items"][0]["text"]
    assert text.startswith("a b xxx") and len(text) == meals.ITEM_TEXT_MAX


def test_shopping_read_is_capped_but_open_is_the_true_count():
    many = [item(f"{n:08d}-0000-4000-8000-000000000000", f"Item {n}", position=n)
            for n in range(meals.SHOPPING_MAX_ITEMS + 25)]
    out = shop(FakeMealie(items=many))
    assert len(out["items"]) == meals.SHOPPING_MAX_ITEMS
    assert out["open"] == meals.SHOPPING_MAX_ITEMS + 25


@pytest.mark.parametrize("body", [[], "x", 5, {"listItems": "x"}, {"listItems": [None, 5]}, {}])
def test_shopping_read_never_raises_on_a_wrong_shaped_body(body):
    fake = FakeMealie()
    inner = fake.handler
    def handler(req):
        if req.url.path == f"/api/households/shopping/lists/{RID2}":
            return httpx.Response(200, json=body)
        return inner(req)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.shopping_tile(c, mcfg(), ENV)
    out = asyncio.run(go())
    assert out["available"] is True and out["items"] == [] and out["open"] == 0


def test_shopping_read_unconfigured_or_tokenless_makes_no_request():
    fake = FakeMealie()
    assert run(fake, lambda c, cfg: meals.shopping_tile(c, cfg, ENV), Config()) == {"available": False}
    out = run(fake, lambda c, cfg: meals.shopping_tile(c, cfg, {}))
    assert out == {"available": False, "needs_auth": True}
    assert fake.calls == []


@pytest.mark.parametrize("status,auth", [(401, True), (403, True), (500, False), (404, False)])
def test_shopping_read_upstream_errors_are_unavailable_and_flag_auth_only_for_401_403(status, auth):
    fake = FakeMealie(items=[item(IID1, "Milk")])
    fake.fail[("GET", f"/api/households/shopping/lists/{RID2}")] = status
    out = shop(fake)
    assert out == {"available": False, "needs_auth": auth}


def test_shopping_read_with_no_list_is_unavailable_not_an_exception():
    out = shop(FakeMealie(lists=[]))
    assert out["available"] is False


def test_shopping_read_does_not_turn_the_dinner_source_red_or_green():
    shop(FakeMealie(items=[item(IID1, "Milk")]))
    assert "meals" not in tiles.SOURCE_STATE or "last_ok" not in tiles.SOURCE_STATE["meals"]
    fake = FakeMealie()
    fake.fail[("GET", f"/api/households/shopping/lists/{RID2}")] = 500
    shop(fake)
    assert not tiles.SOURCE_STATE.get("meals", {}).get("last_error")


def test_shopping_read_transport_error_is_unavailable_and_never_cached():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        raise httpx.ConnectError("down")
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            a = await meals.shopping_tile(c, mcfg(), ENV)
            b = await meals.shopping_tile(c, mcfg(), ENV)
            return a, b
    a, b = asyncio.run(go())
    assert a == b == {"available": False, "needs_auth": False}
    assert calls["n"] == 2 and meals._shop_cache == {}


def test_shopping_read_is_cached_briefly_and_expires(monkeypatch):
    fake = FakeMealie(items=[item(IID1, "Milk")])
    clock = [1000.0]
    monkeypatch.setattr(meals.time, "monotonic", lambda: clock[0])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.shopping_tile(c, mcfg(), ENV)
            await meals.shopping_tile(c, mcfg(), ENV)          # cached
            n1 = len(fake.log)
            clock[0] += meals.SHOPPING_TTL + 1
            await meals.shopping_tile(c, mcfg(), ENV)          # expired
            return n1, len(fake.log)
    n1, n2 = asyncio.run(go())
    assert n2 == n1 * 2, "one list lookup + one list read per uncached call"


def test_a_shopping_read_that_started_before_a_write_does_not_cache_its_answer():
    fake = FakeMealie(items=[item(IID1, "Milk")])
    inner = fake.handler
    def handler(req):
        if req.url.path == f"/api/households/shopping/lists/{RID2}":
            meals._invalidate_shopping()      # a write lands while this read is in flight
        return inner(req)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.shopping_tile(c, mcfg(), ENV)
    asyncio.run(go())
    assert meals._shop_cache == {}


def test_the_wall_refresh_drops_the_shopping_cache_too():
    fake = FakeMealie(items=[item(IID1, "Milk")])
    shop(fake)
    assert meals._shop_cache
    meals.forget_plan()
    assert meals._shop_cache == {}
```

- [ ] **Step 3: Run to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py -q -p no:anyio -k shopping_read`
Expected: FAIL with `AttributeError: module 'family_hub.meals' has no attribute 'shopping_tile'`.

- [ ] **Step 4: Implement**

In `src/family_hub/meals.py`, add constants after `RANDOM_BUDGET_S`:

```python
SHOPPING_TTL = 10.0             # a list changes when someone edits it; the card re-reads every minute anyway
SHOPPING_MAX_ITEMS = 200
ITEM_TEXT_MAX = 120
```

After `_image_cache` add:

```python
# Mealie base -> (expiry monotonic, result). Only good reads are cached.
_shop_cache: dict[str, tuple[float, dict]] = {}
# Bumped by every shopping write (even a failed one) and by the wall's refresh; a read
# that STARTED before it must not cache its pre-write answer after it (same idea as _gen).
_shop_gen = 0
```

Replace `reset_caches` and `forget_plan` bodies and add `_invalidate_shopping`:

```python
def reset_caches() -> None:
    _cache.clear()
    _image_cache.clear()
    _shop_cache.clear()


def forget_plan() -> None:
    """Drop the cached meal plan and shopping list so the next read goes to Mealie
    (the wall's refresh button). Recipe photos stay cached."""
    _invalidate()
    _invalidate_shopping()


def _invalidate_shopping() -> None:
    global _shop_gen
    _shop_gen += 1
    _shop_cache.clear()
```

Add before `async def fetch_image`:

```python
def _shopping_item(raw: dict) -> dict | None:
    """One list entry as the card shows it, or None when it cannot be shown. A
    recipe-derived item has a computed ``display`` ("2 cups flour"); a free-text one
    has just a ``note``."""
    iid = raw.get("id")
    if not valid_uuid(iid):
        return None
    text = raw.get("display")
    if not isinstance(text, str) or not text.strip():
        text = raw.get("note")
    if not isinstance(text, str) or not text.strip():
        return None
    return {"id": iid, "text": " ".join(text.split())[:ITEM_TEXT_MAX],
            "checked": raw.get("checked") is True}


async def shopping_tile(client, cfg, env: dict) -> dict:
    """``{available, needs_auth?, list: {id, name}, items: [{id, text, checked}], open}``.

    Unchecked items first (by Mealie's own order), then checked ones; capped at
    SHOPPING_MAX_ITEMS, with ``open`` still the true unchecked count. Never raises;
    errors are never cached. A failing read says nothing about the dinner tile (the
    shared ``auth_rejected`` flag is the one thing both report)."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"available": False}
    if not mealie_token(env):
        return {"available": False, "needs_auth": True}
    hit = _shop_cache.get(mc["base"])
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    gen = _shop_gen
    try:
        list_id, list_name = await _shopping_list(client, mc, env)
        r = await client.get(f"{mc['base']}/api/households/shopping/lists/{list_id}",
                             headers=_headers(env), timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
        log.warning("meals shopping unavailable: %s", e)
        _note_auth(e)
        return {"available": False, "needs_auth": _auth_failed(e)}
    raw_items = body.get("listItems") if isinstance(body, dict) else None
    rows = []
    for n, raw in enumerate(raw_items if isinstance(raw_items, list) else []):
        shaped = _shopping_item(raw) if isinstance(raw, dict) else None
        if shaped is not None:
            pos = raw.get("position")
            rows.append((shaped["checked"], pos if _is_int(pos) else n, n, shaped))
    rows.sort(key=lambda t: t[:3])
    result = {"available": True, "list": {"id": list_id, "name": list_name},
              "items": [t[3] for t in rows[:SHOPPING_MAX_ITEMS]],
              "open": sum(1 for t in rows if not t[0])}
    if gen == _shop_gen:             # a write landed while we were reading: don't cache the old list
        _shop_cache[mc["base"]] = (time.monotonic() + SHOPPING_TTL, result)
    return result
```

- [ ] **Step 5: Run to verify they pass, then the whole file**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py -q -p no:anyio`
Expected: all pass (the pre-existing meals tests included).

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/meals.py tests/test_meals.py
git commit -m "feat(meals): fail-soft Mealie shopping-list read for the Shopping card"
```
(The changelog entry lands in Task 3, which is the first commit that makes the change user-visible; if the pre-commit hook blocks this commit, add the Task 3 changelog entry now and amend its wording there.)

---

### Task 2: Shopping writes (add, check, delete)

**Files:**
- Modify: `src/family_hub/meals.py` (after `shopping_tile`)
- Test: `tests/test_meals.py`

**Interfaces:**
- Consumes: Task 1's `_invalidate_shopping`, `ITEM_TEXT_MAX`; existing `_shopping_list`, `_fail`, `_headers`, `valid_uuid`, `mealie_token`, `TIMEOUT`.
- Produces: `async def add_shopping_item(client, cfg, env, text) -> dict`, `async def set_shopping_checked(client, cfg, env, item_id, checked) -> dict`, `async def delete_shopping_item(client, cfg, env, item_id) -> dict`, each returning `{"ok": True}` or `{"ok": False, "error", "status", "needs_auth"?}` and never raising. Helpers `_clean_item_text`, `_own_item`, `_shopping_write`, constant `_ITEM_KEEP`.

- [ ] **Step 1: Write the failing tests** (append `# ---- shopping writes`)

```python
# ----------------------------------------------------------- shopping writes

def add(fake, text, cfg=None, env=ENV):
    return run(fake, lambda c, cfg_: meals.add_shopping_item(c, cfg_, env, text), cfg)


def check(fake, iid, checked, cfg=None, env=ENV):
    return run(fake, lambda c, cfg_: meals.set_shopping_checked(c, cfg_, env, iid, checked), cfg)


def delete(fake, iid, cfg=None, env=ENV):
    return run(fake, lambda c, cfg_: meals.delete_shopping_item(c, cfg_, env, iid), cfg)


def test_add_posts_a_free_text_item_to_the_configured_list():
    fake = FakeMealie()
    assert add(fake, "  Paper   towels ") == {"ok": True}
    post = next(c for c in fake.calls if c["method"] == "POST" and c["path"].endswith("/shopping/items"))
    assert post["body"] == {"shoppingListId": RID2, "note": "Paper towels", "quantity": 1, "checked": False}
    assert [i["note"] for i in fake.items] == ["Paper towels"]


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None, 5, ["x"], {"a": 1}, "x" * (meals.ITEM_TEXT_MAX + 1)])
def test_add_rejects_blank_non_text_and_over_long_before_any_request(text):
    fake = FakeMealie()
    out = add(fake, text)
    assert out["ok"] is False and out["status"] == 422
    assert fake.calls == []


def test_add_accepts_emoji_and_the_exact_length_limit():
    fake = FakeMealie()
    assert add(fake, "🍌 bananas")["ok"] and add(fake, "x" * meals.ITEM_TEXT_MAX)["ok"]


def test_check_sends_the_whole_item_with_only_checked_changed():
    fake = FakeMealie(items=[item(IID1, "Milk", position=3, quantity=2, foodId="f1", unitId="u1", labelId="l1")])
    assert check(fake, IID1, True) == {"ok": True}
    put = next(c for c in fake.calls if c["method"] == "PUT")
    assert put["path"] == f"/api/households/shopping/items/{IID1}"
    assert put["body"] == {"note": "Milk", "quantity": 2, "position": 3, "foodId": "f1", "unitId": "u1",
                           "labelId": "l1", "extras": {}, "shoppingListId": RID2, "checked": True}
    assert fake.items[0]["checked"] is True
    assert check(fake, IID1, False) == {"ok": True} and fake.items[0]["checked"] is False


@pytest.mark.parametrize("iid", ["", "not-a-uuid", "../../x", IID1 + "\n", IID1.upper() + "x", None, 5])
def test_check_and_delete_reject_a_bad_item_id_before_any_request(iid):
    fake = FakeMealie(items=[item(IID1, "Milk")])
    for out in (check(fake, iid, True), delete(fake, iid)):
        assert out["ok"] is False and out["status"] == 422
    assert fake.calls == []


@pytest.mark.parametrize("checked", ["yes", 1, 0, None, "true", [True]])
def test_check_rejects_a_non_boolean_before_any_request(checked):
    fake = FakeMealie(items=[item(IID1, "Milk")])
    out = check(fake, IID1, checked)
    assert out["ok"] is False and out["status"] == 422 and fake.calls == []


def test_check_and_delete_an_item_that_is_gone_are_a_404_and_write_nothing():
    fake = FakeMealie(items=[])
    for out in (check(fake, IID1, True), delete(fake, IID1)):
        assert out == {"ok": False, "error": "that item is not on the list", "status": 404}
    assert not [c for c in fake.calls if c["method"] in ("PUT", "DELETE")]


def test_check_an_item_from_another_list_is_a_404_and_never_written():
    fake = FakeMealie(items=[item(IID1, "Milk", list_id=OTHER_LIST)])
    assert check(fake, IID1, True)["status"] == 404
    assert delete(fake, IID1)["status"] == 404
    assert not [c for c in fake.calls if c["method"] in ("PUT", "DELETE")]
    assert fake.items[0]["checked"] is False


def test_delete_removes_only_that_item():
    fake = FakeMealie(items=[item(IID1, "Milk"), item(IID2, "Eggs")])
    assert delete(fake, IID1) == {"ok": True}
    assert [i["id"] for i in fake.items] == [IID2]


def test_writes_without_a_token_or_config_are_refused_without_a_request():
    fake = FakeMealie(items=[item(IID1, "Milk")])
    for out in (add(fake, "x", env={}), check(fake, IID1, True, env={}), delete(fake, IID1, env={})):
        assert out["ok"] is False and out["needs_auth"] is True and out["status"] == 503
    for out in (add(fake, "x", cfg=Config()), check(fake, IID1, True, cfg=Config()),
                delete(fake, IID1, cfg=Config())):
        assert out["ok"] is False and out["status"] == 404
    assert fake.calls == []


def test_writes_with_no_shopping_list_are_a_409_with_a_reason():
    fake = FakeMealie(lists=[], items=[item(IID1, "Milk")])
    for out in (add(fake, "x"), check(fake, IID1, True), delete(fake, IID1)):
        assert out["ok"] is False and out["status"] == 409 and out["error"]


@pytest.mark.parametrize("method,path_start", [("POST", "/api/households/shopping/items"),
                                               ("PUT", "/api/households/shopping/items/"),
                                               ("DELETE", "/api/households/shopping/items/")])
def test_write_upstream_failure_is_a_502_with_a_reason(method, path_start):
    fake = FakeMealie(items=[item(IID1, "Milk")])
    fake.fail[(method, path_start)] = 500
    out = {"POST": lambda: add(fake, "x"), "PUT": lambda: check(fake, IID1, True),
           "DELETE": lambda: delete(fake, IID1)}[method]()
    assert out["ok"] is False and out["status"] == 502 and out["error"] == "Mealie answered 500"


def test_write_rejected_token_is_flagged_for_the_wall():
    fake = FakeMealie(items=[item(IID1, "Milk")])
    fake.fail[("PUT", "/api/households/shopping/items/")] = 401
    out = check(fake, IID1, True)
    assert out["status"] == 502 and out["needs_auth"] is True
    assert tiles.SOURCE_STATE["meals"]["auth_rejected"] is True


def test_write_with_a_junk_reply_fails_cleanly():
    def handler(req):
        if req.url.path == "/api/households/shopping/lists":
            return httpx.Response(200, content=b"<html>")
        return httpx.Response(404)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.add_shopping_item(c, mcfg(), ENV, "x")
    out = asyncio.run(go())
    assert out["ok"] is False and out["status"] == 502


def test_every_write_drops_the_cached_list_even_when_it_fails():
    fake = FakeMealie(items=[item(IID1, "Milk")])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            a = await meals.shopping_tile(c, mcfg(), ENV)
            await meals.add_shopping_item(c, mcfg(), ENV, "Eggs")
            b = await meals.shopping_tile(c, mcfg(), ENV)
            fake.fail[("PUT", "/api/households/shopping/items/")] = 500
            await meals.set_shopping_checked(c, mcfg(), ENV, IID1, True)      # fails
            assert meals._shop_cache == {}, "a failed write still drops the cache"
            return a, b
    a, b = asyncio.run(go())
    assert [i["text"] for i in a["items"]] == ["Milk"]
    assert [i["text"] for i in b["items"]] == ["Milk", "Eggs"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py -q -p no:anyio -k "add_ or check_ or delete_ or write"`
Expected: FAIL with `AttributeError: ... no attribute 'add_shopping_item'`.

- [ ] **Step 3: Implement** (in `meals.py`, right after `shopping_tile`)

```python
# What a check/un-check sends back. Mealie's update replaces the item, so the
# fields that define it ride along unchanged; read-only ones (ids, timestamps,
# computed display) are left out. Task 0's live probe confirmed Mealie preserves
# food/unit/quantity through exactly this body.
_ITEM_KEEP = ("note", "quantity", "position", "foodId", "unitId", "labelId", "extras")
_NOT_ON_LIST = {"ok": False, "error": "that item is not on the list", "status": 404}


def _clean_item_text(text: object) -> str | None:
    """A quick-add as stored: whitespace collapsed, 1 to ITEM_TEXT_MAX characters,
    else None (including anything that is not text)."""
    if not isinstance(text, str):
        return None
    clean = " ".join(text.split())
    return clean if 0 < len(clean) <= ITEM_TEXT_MAX else None


async def _own_item(client, mc: dict, env: dict, list_id: str, item_id: str) -> dict | None:
    """The item, only if it exists AND sits on the configured list. An id from
    another list, another household or one Mealie has since deleted is None: the
    hub never writes to something it did not just confirm is on its list."""
    r = await client.get(f"{mc['base']}/api/households/shopping/items/{item_id}",
                         headers=_headers(env), timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    found = r.json()
    if not isinstance(found, dict) or str(found.get("shoppingListId", "")).lower() != list_id.lower():
        return None
    return found


async def _shopping_write(client, cfg, env: dict, run) -> dict:
    """The shared frame of the three writes: refuse what cannot be tried, resolve the
    list, run ``run(mc, list_id)``, and turn every failure into the usual
    ``{ok: False, error, status}`` (never raising). The cache is dropped whatever
    happens: Mealie may have changed even when a call failed."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"ok": False, "error": "Meals is not configured", "status": 404}
    if not mealie_token(env):
        return {"ok": False, "error": "MEALIE_API_TOKEN is not set", "status": 503,
                "needs_auth": True}
    try:
        list_id, _name = await _shopping_list(client, mc, env)
        return await run(mc, list_id)
    except json.JSONDecodeError as e:     # before ValueError (it is one): Mealie sent junk, not "no list"
        log.warning("meals shopping write: non-JSON reply: %s", e)
        return {**_fail(e), "status": 502}
    except ValueError as e:
        return {"ok": False, "error": str(e)[:120], "status": 409}
    except httpx.HTTPError as e:
        log.warning("meals shopping write failed: %s", e)
        return {**_fail(e), "status": 502}
    finally:
        _invalidate_shopping()


async def add_shopping_item(client, cfg, env: dict, text: object) -> dict:
    """Quick add: a free-text item on the configured list."""
    clean = _clean_item_text(text)
    if clean is None:
        return {"ok": False, "error": f"an item is 1 to {ITEM_TEXT_MAX} characters", "status": 422}

    async def run(mc, list_id):
        r = await client.post(f"{mc['base']}/api/households/shopping/items",
                              json={"shoppingListId": list_id, "note": clean, "quantity": 1,
                                    "checked": False},
                              headers=_headers(env), timeout=TIMEOUT)
        r.raise_for_status()
        return {"ok": True}
    return await _shopping_write(client, cfg, env, run)


async def set_shopping_checked(client, cfg, env: dict, item_id: object, checked: object) -> dict:
    """Check or un-check an item. Mealie's update needs the whole item, so read it,
    set ``checked``, write it back."""
    if not valid_uuid(item_id):
        return {"ok": False, "error": "not an item id", "status": 422}
    if not isinstance(checked, bool):
        return {"ok": False, "error": "checked must be true or false", "status": 422}

    async def run(mc, list_id):
        found = await _own_item(client, mc, env, list_id, item_id)
        if found is None:
            return dict(_NOT_ON_LIST)
        body = {k: found[k] for k in _ITEM_KEEP if k in found}
        body.update({"shoppingListId": list_id, "checked": checked})
        r = await client.put(f"{mc['base']}/api/households/shopping/items/{item_id}",
                             json=body, headers=_headers(env), timeout=TIMEOUT)
        r.raise_for_status()
        return {"ok": True}
    return await _shopping_write(client, cfg, env, run)


async def delete_shopping_item(client, cfg, env: dict, item_id: object) -> dict:
    """Delete an item from the configured list."""
    if not valid_uuid(item_id):
        return {"ok": False, "error": "not an item id", "status": 422}

    async def run(mc, list_id):
        if await _own_item(client, mc, env, list_id, item_id) is None:
            return dict(_NOT_ON_LIST)
        r = await client.delete(f"{mc['base']}/api/households/shopping/items/{item_id}",
                                headers=_headers(env), timeout=TIMEOUT)
        r.raise_for_status()
        return {"ok": True}
    return await _shopping_write(client, cfg, env, run)
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py -q -p no:anyio`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/family_hub/meals.py tests/test_meals.py
git commit -m "feat(meals): add, check and delete shopping items, list-membership checked"
```

---

### Task 3: Routes, demo payload, changelog

**Files:**
- Modify: `src/family_hub/app.py` (after `mealie_shopping`, ~line 3105)
- Modify: `src/family_hub/demo.py` (after `demo_meals`)
- Modify: `CHANGELOG.md`
- Test: `tests/test_meals.py` (route tests), `tests/test_demo.py`

**Interfaces:**
- Consumes: Task 1/2 functions; `_meals_reply`, `_http`, `cfg`, `DEMO`, `fdemo`.
- Produces: `GET /api/mealie/shopping` -> the read; `POST /api/mealie/shopping/items` `{text}`; `PUT /api/mealie/shopping/items/{item_id}` `{checked}`; `DELETE /api/mealie/shopping/items/{item_id}`. Writes return `{"ok": true}` or an HTTP error with the reason in `detail`. `demo.demo_shopping() -> dict` in the read's shape.

- [ ] **Step 1: Write the failing route and demo tests**

Append to `tests/test_meals.py` (routes section; `app_env` yields `(appmod, client, fake)`):

```python
def test_route_shopping_read_and_writes_round_trip(app_env):
    appmod, c, fake = app_env
    fake.items.append(item(IID1, "Milk"))
    got = c.get("/api/mealie/shopping").json()
    assert got["available"] is True and got["items"] == [{"id": IID1, "text": "Milk", "checked": False}]
    assert c.post("/api/mealie/shopping/items", json={"text": "Eggs"}).json() == {"ok": True}
    assert c.put(f"/api/mealie/shopping/items/{IID1}", json={"checked": True}).json() == {"ok": True}
    after = c.get("/api/mealie/shopping").json()
    assert [(i["text"], i["checked"]) for i in after["items"]] == [("Eggs", False), ("Milk", True)]
    assert c.delete(f"/api/mealie/shopping/items/{IID1}").json() == {"ok": True}
    assert [i["text"] for i in c.get("/api/mealie/shopping").json()["items"]] == ["Eggs"]


def test_route_shopping_rejections_are_real_http_statuses_with_a_reason(app_env):
    appmod, c, fake = app_env
    fake.items.append(item(IID1, "Milk"))
    r = c.post("/api/mealie/shopping/items", json={"text": "   "})
    assert r.status_code == 422 and "1 to" in r.json()["detail"]
    assert c.post("/api/mealie/shopping/items", json={}).status_code == 422
    assert c.put("/api/mealie/shopping/items/not-a-uuid", json={"checked": True}).status_code == 422
    assert c.put(f"/api/mealie/shopping/items/{IID1}", json={}).status_code == 422
    assert c.put(f"/api/mealie/shopping/items/{IID2}", json={"checked": True}).status_code == 404
    assert c.delete("/api/mealie/shopping/items/..%2F..%2Fx").status_code in (404, 422)
    assert c.delete(f"/api/mealie/shopping/items/{IID2}").status_code == 404
    assert not [x for x in fake.calls if x["method"] in ("PUT", "DELETE")]


def test_route_shopping_upstream_down_is_a_502_with_a_reason(app_env):
    appmod, c, fake = app_env
    fake.fail[("POST", "/api/households/shopping/items")] = 500
    r = c.post("/api/mealie/shopping/items", json={"text": "Eggs"})
    assert r.status_code == 502 and r.json()["detail"] == "Mealie answered 500"
    fake.fail.clear()
    fake.fail[("GET", "/api/households/shopping/lists/")] = 500
    assert c.get("/api/mealie/shopping").json() == {"available": False, "needs_auth": False}


def test_every_shopping_write_route_holds_the_write_lock(app_env):
    """A check is read-modify-write against Mealie: two phones tapping at once must not
    interleave, so each write route runs inside the one lock."""
    import inspect
    appmod, c, fake = app_env
    for fn in (appmod.mealie_shopping_add, appmod.mealie_shopping_check, appmod.mealie_shopping_delete):
        assert "async with _shopping_write_lock" in inspect.getsource(fn), fn.__name__
```

Append to `tests/test_demo.py` after the meals demo tests:

```python
def test_demo_shopping_tile_shows_the_card_best_states(demo_client):
    """A live-shaped list with open and checked items, no Mealie hit."""
    t = demo_client.get("/api/mealie/shopping").json()
    assert t["available"] is True and t["list"]["name"]
    items = t["items"]
    assert len(items) >= 8, "enough rows that the card's list scrolls"
    assert all(set(i) == {"id", "text", "checked"} for i in items), "the shape meals.shopping_tile serves"
    assert any(i["checked"] for i in items) and any(not i["checked"] for i in items)
    assert [i["checked"] for i in items] == sorted(i["checked"] for i in items), "unchecked first"
    assert t["open"] == sum(1 for i in items if not i["checked"])


def test_demo_shopping_writes_change_nothing_and_never_reach_mealie(demo_client):
    before = demo_client.get("/api/mealie/shopping").json()
    iid = before["items"][0]["id"]
    assert demo_client.post("/api/mealie/shopping/items", json={"text": "Eggs"}).json() == {"ok": True, "demo": True}
    assert demo_client.put(f"/api/mealie/shopping/items/{iid}", json={"checked": True}).json() == {"ok": True, "demo": True}
    assert demo_client.delete(f"/api/mealie/shopping/items/{iid}").json() == {"ok": True, "demo": True}
    assert demo_client.get("/api/mealie/shopping").json() == before
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py tests/test_demo.py -q -p no:anyio -k "shopping"`
Expected: FAIL (`404` / missing attributes).

- [ ] **Step 3: Implement the demo payload** (`src/family_hub/demo.py`, after `demo_meals`)

```python
def demo_shopping() -> dict:
    """A live-shaped shopping list (matches meals.shopping_tile): enough open items that
    the card's list scrolls, a couple already checked off below them. The ids are made
    up; the demo's shopping writes are no-ops, so nothing here ever changes."""
    names = ["Milk", "Eggs", "Sourdough bread", "Bananas", "Chicken thighs", "Lemons",
             "Paper towels", "Cheddar", "Salad kit"]
    checked = ["Greek yogurt", "Butter"]
    items = [{"id": f"00000000-0000-4000-8000-{n:012d}", "text": t, "checked": False}
             for n, t in enumerate(names, start=1)]
    items += [{"id": f"00000000-0000-4000-8000-{n:012d}", "text": t, "checked": True}
              for n, t in enumerate(checked, start=len(names) + 1)]
    return {"available": True, "list": {"id": "00000000-0000-4000-8000-0000000000ff", "name": "Groceries"},
            "items": items, "open": len(names)}
```

- [ ] **Step 4: Implement the routes** (`src/family_hub/app.py`, directly after `mealie_shopping`)

```python
# --- meals: the shopping list (read, quick add, check/un-check, delete) -------
#
# One lock serializes the writes: a check is read-modify-write against Mealie, so two
# phones tapping the same item at once must not interleave. Single process, so a plain
# asyncio lock (like _meals_write_lock).
_shopping_write_lock = asyncio.Lock()


class ShoppingAddIn(BaseModel):
    text: str


class ShoppingCheckIn(BaseModel):
    checked: bool


@app.get("/api/mealie/shopping")
async def mealie_shopping_list():
    if DEMO:
        return fdemo.demo_shopping()      # canned list; no Mealie hit
    return await meals.shopping_tile(_http, cfg, os.environ)


@app.post("/api/mealie/shopping/items")
async def mealie_shopping_add(body: ShoppingAddIn):
    if DEMO:
        return {"ok": True, "demo": True}
    async with _shopping_write_lock:
        return _meals_reply(await meals.add_shopping_item(_http, cfg, os.environ, body.text))


@app.put("/api/mealie/shopping/items/{item_id}")
async def mealie_shopping_check(item_id: str, body: ShoppingCheckIn):
    if DEMO:
        return {"ok": True, "demo": True}
    async with _shopping_write_lock:
        return _meals_reply(await meals.set_shopping_checked(
            _http, cfg, os.environ, item_id, body.checked))


@app.delete("/api/mealie/shopping/items/{item_id}")
async def mealie_shopping_delete(item_id: str):
    if DEMO:
        return {"ok": True, "demo": True}
    async with _shopping_write_lock:
        return _meals_reply(await meals.delete_shopping_item(_http, cfg, os.environ, item_id))
```

Note: pydantic's default (lax) mode would coerce `{"checked": 1}` to `True` at the route; `set_shopping_checked` independently refuses non-bool, so direct callers are covered too. Keep `ShoppingCheckIn.checked` as plain `bool`.

- [ ] **Step 5: Add the changelog entry** under `## [Unreleased]` in `CHANGELOG.md` (create an `### Added` block above `### Changed` if none exists):

```markdown
### Added
- Shopping: the Mealie shopping list as a native wall card (left column, beside the
  To-Do card) and a section on the phone's Meals tab. Check items off and un-check
  them, quick-add an item, delete one. The list scrolls inside the card like the meal
  plan. It follows the Meals (Mealie) switch; To-Dos can be switched off to give it the
  room. Backend: `GET /api/mealie/shopping`, `POST /api/mealie/shopping/items`,
  `PUT`/`DELETE /api/mealie/shopping/items/{id}`; every write checks the item is on the
  configured list first.
```

- [ ] **Step 6: Run both Python files, then the full Python suite**

Run: `PYTHONPATH=src python -m pytest tests/test_meals.py tests/test_demo.py -q -p no:anyio` then `PYTHONPATH=src python -m pytest -q -p no:anyio`
Expected: all pass; no skips you did not already have (`-ra` lists them).

- [ ] **Step 7: Commit**

```bash
git add src/family_hub/app.py src/family_hub/demo.py tests/test_meals.py tests/test_demo.py CHANGELOG.md
git commit -m "feat(meals): shopping routes and demo payload"
```

---

### Task 4: The card, read-only (markup, CSS, render, fetch, poll)

**Files:**
- Modify: `src/family_hub/web/static/index.html` (after the `#todo-slot` section, line ~147)
- Modify: `src/family_hub/web/static/hub.js` (state vars after line ~39; render/fetch block after `mealsAct`, before `let fitDebounce`; `renderIntegrations` flip block ~5206; bootstrap/poll ~5990-6001)
- Modify: `src/family_hub/web/static/styles.css`
- Test: `tests/js/hub-dom.test.mjs`, `tests/test_static.py`

**Interfaces:**
- Consumes: `j`, `sectionHead(label, {chip})`, `escapeHtml`, `showToast`, `hubData`, `TILE_FAIL_LIMIT`, `POLL_MS`; GET `/api/mealie/shopping`.
- Produces (for Task 5): globals `shopData`, `shopSeq`, `shopFails`, `shopScrollAt`, `shopMenuOpen`, `shopMenuTimer`, `shopAddBusy`, `shopBusy`, constants `SHOP_MENU_IDLE_MS`, `SHOP_SCROLL_KEEP_MS`, `SHOP_LOCK_ATTR`; functions `shopItems(s)`, `shoppingRowHtml(it)`, `shoppingCardHtml(items)`, `renderShopping(s = shopData)`, `fetchShopping()`. Markup contract: `#shopping-slot`; `form#shop-add-form` containing `input#shop-add-input.txt-input` and a submit button; `.shop-rows` containing `.shop-row[.done]` rows each with `button[data-shop-check]` and `button[data-shop-open]`.

- [ ] **Step 1: Write the failing JS tests** (append to `tests/js/hub-dom.test.mjs` after the Meals tests; also add `'shopping-slot'` to `SEEDED_IDS` at line ~36)

```js
// ---- the native Shopping card ----

const IID_A = '11111111-1111-4111-8111-111111111111';
const IID_B = '22222222-2222-4222-8222-222222222222';
const IID_C = '33333333-3333-4333-8333-333333333333';
const shopItem = (id, text, checked = false) => ({ id, text, checked });
const SHOP_LIST = () => ({ available: true, list: { id: 'l', name: 'Groceries' }, open: 2, items: [
  shopItem(IID_A, 'Milk'), shopItem(IID_B, 'Eggs'), shopItem(IID_C, 'Butter', true)] });

function shopHtml(payload) {
  const { document, sandbox, fire } = newHub();
  vm.runInContext(LISTED, sandbox);
  sandbox.renderShopping(payload);
  return { html: document.getElementById('shopping-slot').innerHTML, document, sandbox, fire };
}

test('renderShopping: loading placeholder, unavailable and needs-a-token notes, header always stands', () => {
  assert.match(shopHtml(null).html, /wx-loading/);
  assert.match(shopHtml({ available: false }).html, /Shopping unavailable/);
  assert.match(shopHtml({ available: false, needs_auth: true }).html, /Shopping needs a Mealie token/);
  assert.match(shopHtml(null).html, /<h2>Shopping<\/h2>/);
});

test('renderShopping: unlisted (no Mealie on this hub) and nothing to show renders nothing', () => {
  const { document, sandbox } = newHub();
  vm.runInContext("hubData = { integrations: [] };", sandbox);
  sandbox.renderShopping({ available: false });
  assert.equal(document.getElementById('shopping-slot').innerHTML, '');
});

test('renderShopping: the add field sits above the scrolling rows; open count is the header chip', () => {
  const { html } = shopHtml(SHOP_LIST());
  assert.match(html, /<span class="shead-chip">2<\/span>/);
  assert.ok(html.indexOf('id="shop-add-form"') < html.indexOf('class="shop-rows"'),
    'the quick-add stays outside the scroller');
  assert.match(html, /id="shop-add-input" class="txt-input"/, 'the on-screen keyboard serves .txt-input');
});

test('renderShopping: unchecked first, checked last and marked done; every control is a real button', () => {
  const { html } = shopHtml(SHOP_LIST());
  const order = [...html.matchAll(/data-shop-check="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, [IID_A, IID_B, IID_C]);
  assert.match(html, new RegExp(`shop-row done"><button type="button" class="shop-check" data-shop-check="${IID_C}" aria-pressed="true" aria-label="Mark not bought: Butter"`));
  assert.match(html, new RegExp(`class="shop-check" data-shop-check="${IID_A}" aria-pressed="false" aria-label="Mark bought: Milk"`));
  assert.match(html, new RegExp(`<button type="button" class="shop-text" data-shop-open="${IID_A}"`));
});

test('renderShopping: the client orders unchecked first even if the payload does not', () => {
  const out = shopHtml({ ...SHOP_LIST(), items: [shopItem(IID_C, 'Butter', true), shopItem(IID_A, 'Milk')] }).html;
  assert.ok(out.indexOf(IID_A) < out.indexOf(IID_C));
});

test('renderShopping: an empty list has its own empty state, not a blank card', () => {
  assert.match(shopHtml({ ...SHOP_LIST(), items: [], open: 0 }).html, /Nothing on the list/);
});

test('renderShopping: item text and ids from Mealie are inert', () => {
  const evil = { available: true, list: { id: 'l', name: 'x' }, open: 1, items: [
    shopItem(IID_A, '<img src=x onerror=alert(1)>'), shopItem('"><svg onload=alert(2)>', '<script>x</script>')] };
  const html = shopHtml(evil).html;
  assert.doesNotMatch(html, /<script|<svg|<img src=x/, 'no live markup from upstream text');
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('renderShopping: a malformed payload degrades to a note, never throws', () => {
  for (const items of [null, 'x', 5, {}, [null, 5, {}], [{ id: 5 }]]) {
    const r = shopHtml({ available: true, list: { id: 'l', name: 'x' }, open: 0, items });
    assert.match(r.html, /Nothing on the list|wx-offline/);
  }
});

test('renderShopping: the open count comes from the server so a capped list still reads true', () => {
  assert.match(shopHtml({ ...SHOP_LIST(), open: 340 }).html, /<span class="shead-chip">340<\/span>/);
});

const shopFetchLog = (sandbox, { list = SHOP_LIST(), failGet = false } = {}) => {
  const calls = [];
  sandbox.fetch = async (url, opts = {}) => {
    calls.push({ url, method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null });
    if (failGet && !opts.method) return { ok: false, status: 502, json: async () => ({ detail: 'down' }) };
    return { ok: true, status: 200, json: async () => (url === '/api/mealie/shopping' ? list : { ok: true }) };
  };
  return calls;
};

test('fetchShopping: paints the list, keeps the last good one through transient failures, then gives up', async () => {
  const { document, sandbox } = newHub();
  vm.runInContext(LISTED, sandbox);
  shopFetchLog(sandbox);
  await sandbox.fetchShopping();
  assert.match(document.getElementById('shopping-slot').innerHTML, /data-shop-check/);
  shopFetchLog(sandbox, { failGet: true });
  await sandbox.fetchShopping();                       // 1st failure: last good card stays
  assert.match(document.getElementById('shopping-slot').innerHTML, /data-shop-check/);
  await sandbox.fetchShopping(); await sandbox.fetchShopping();   // reaches TILE_FAIL_LIMIT
  assert.match(document.getElementById('shopping-slot').innerHTML, /Shopping unavailable/);
});

test('fetchShopping: a late older reply never repaints over a newer one', async () => {
  const { document, sandbox } = newHub();
  vm.runInContext(LISTED, sandbox);
  let release;
  const slow = new Promise((r) => { release = r; });
  let n = 0;
  sandbox.fetch = async () => {
    n += 1;
    if (n === 1) { await slow; return { ok: true, status: 200, json: async () => ({ ...SHOP_LIST(), items: [shopItem(IID_A, 'OLD')], open: 1 }) }; }
    return { ok: true, status: 200, json: async () => ({ ...SHOP_LIST(), items: [shopItem(IID_B, 'NEW')], open: 1 }) };
  };
  const first = sandbox.fetchShopping();
  await sandbox.fetchShopping();
  release(); await first;
  const html = document.getElementById('shopping-slot').innerHTML;
  assert.match(html, /NEW/); assert.doesNotMatch(html, /OLD/);
});

test('fetchShopping: a hub whose registry lacks Mealie never asks', async () => {
  const { sandbox } = newHub();
  vm.runInContext("hubData = { integrations: [{ id: 'chores', enabled: true }] };", sandbox);
  const calls = shopFetchLog(sandbox);
  await sandbox.fetchShopping();
  assert.equal(calls.length, 0);
});
```

Add static guards to `tests/test_static.py` (after `test_meals_following_days_scroll_on_the_wall_and_not_on_the_phone`):

```python
def test_shopping_card_slot_and_hide_hook_are_wired():
    """The Shopping card (operator, 2026-10-05): its slot sits in the wall's left column
    beside the To-Do card, the mealie integration's switch hides it, and its on-screen-
    keyboard field is one the keyboard serves."""
    index = (STATIC / "index.html").read_text()
    hub = (STATIC / "hub.js").read_text()
    left = index.split('class="col-left"')[1].split('class="col-mid"')[0]
    assert left.index('id="todo-slot"') < left.index('id="shopping-slot"'), "Shopping sits under the To-Do card"
    assert re.search(r"body\.integ-off-mealie[^\{]*#shopping-slot[^\{]*\{[^}]*display:\s*none", CSS), \
        "turning Meals (Mealie) off must hide the Shopping card"
    assert re.search(r'id="shop-add-input" class="txt-input"', hub), \
        "the quick-add must carry .txt-input, the class the on-screen keyboard (osk.js OSK_SEL) serves"


def test_shopping_list_scrolls_inside_its_card_on_the_wall():
    """Like the meal plan: the rows scroll inside the card, the quick-add stays above the
    scroller, so a long list never makes the left column taller than the screen."""
    rule = re.search(r"(?m)^\.shop-rows\s*\{([^}]*max-height[^}]*)\}", CSS)
    assert rule, "the wall's .shop-rows rule needs a max-height"
    body = rule.group(1)
    px = int(re.search(r"max-height:\s*(\d+)px", body).group(1))
    assert 150 <= px <= 280, f"max-height {px}px: about four rows (a row is ~44px) with the next one peeking"
    assert re.search(r"overflow-y:\s*auto", body), "the list must scroll"
    assert re.search(r"overscroll-behavior:\s*contain", body), "a scroll inside the list must not drag the wall page"
    hub = (STATIC / "hub.js").read_text()
    card = hub[hub.index("function shoppingCardHtml"):]
    assert card.index('id="shop-add-form"') < card.index('class="shop-rows"'), "the quick-add stays outside the scroller"
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/hub-dom.test.mjs` and `PYTHONPATH=src python -m pytest tests/test_static.py -q -p no:anyio -k shopping`
Expected: FAIL (`renderShopping is not a function`; missing slot).

- [ ] **Step 3: Add the slot** (`index.html`, directly after the `todo-slot` section)

```html
        <section class="shopping-slot" id="shopping-slot" aria-label="Shopping"></section>
```

- [ ] **Step 4: Add state** (`hub.js`, directly after the `mealsBusy` line, ~39)

```js
let shopData = null;         // last /api/mealie/shopping payload (native Shopping card)
let shopFails = 0;           // consecutive shopping fetch failures (see fetchShopping)
let shopSeq = 0;             // numbers shopping fetches so a late older reply never repaints over a newer one
let shopScrollAt = 0;        // when the list was last scrolled or used by hand
let shopMenuOpen = null;     // the item id whose action row (delete) is open: one at a time
let shopMenuTimer = null;
let shopAddBusy = false;     // one quick add at a time
const SHOP_MENU_IDLE_MS = 15000;     // an open row menu closes itself after this
const SHOP_SCROLL_KEEP_MS = 30000;   // keep a hand-scrolled list in place this long, then return to the top
const shopBusy = new Set();  // item ids with a write in flight (their check is disabled meanwhile)
// an HTML attribute, not a class: held in a constant so the static class guard leaves it alone
const SHOP_LOCK_ATTR = ' disabled';
```

- [ ] **Step 5: Add render + fetch** (`hub.js`, directly before `let fitDebounce = null;`)

```js
/* ---------------------------------------------------- native Shopping card */

/* The Mealie shopping list (operator, 2026-10-05): a card in the wall's left column
   beside the To-Do card (switch To-Dos off in Settings to give it the room) and a
   section on the phone's Meals tab. It rides the Meals (Mealie) switch. Check an item
   off with one tap on its circle; tap its text to open an inline row menu (delete) --
   inline, not a popover, because the list scrolls inside the card and would clip one.
   The quick-add field sits ABOVE the scroller so a long list never moves it. */

// unchecked first, then checked, whatever order the payload came in; drops anything unusable
function shopItems(s) {
  const raw = s && Array.isArray(s.items) ? s.items : [];
  const ok = raw.filter((i) => i && typeof i.id === 'string' && typeof i.text === 'string');
  return ok.filter((i) => !i.checked).concat(ok.filter((i) => i.checked));
}

function shoppingRowHtml(it) {
  const t = escapeHtml(it.text);
  const id = escapeHtml(it.id);
  const open = shopMenuOpen === it.id;
  const lock = shopBusy.has(it.id) ? SHOP_LOCK_ATTR : '';
  const label = it.checked ? 'Mark not bought' : 'Mark bought';
  return `<div class="shop-row${it.checked ? ' done' : ''}">`
    + `<button type="button" class="shop-check" data-shop-check="${id}" aria-pressed="${!!it.checked}"`
    + ` aria-label="${label}: ${t}"${lock}><span class="todo-check">✓</span></button>`
    + `<button type="button" class="shop-text" data-shop-open="${id}" aria-expanded="${open}"`
    + `${open ? ' aria-controls="shop-menu"' : ''}>${t}</button></div>`
    + (open
      ? `<div class="shop-menu" id="shop-menu" role="group" aria-label="Actions for ${t}">`
        + `<button type="button" class="meal-btn shop-del" data-shop-del="${id}"${lock}>Delete</button></div>`
      : '');
}

function shoppingCardHtml(items) {
  return `<article class="card shop-card">`
    + `<form id="shop-add-form" class="shop-add" autocomplete="off">`
    + `<input id="shop-add-input" class="txt-input" maxlength="120" placeholder="Add an item…"`
    + ` autocomplete="off" aria-label="Add a shopping item">`
    + `<button class="cal-nav-btn" type="submit">Add</button></form>`
    + (items.length
      ? `<div class="shop-rows">${items.map(shoppingRowHtml).join('')}</div>`
      : `<div class="shop-empty">Nothing on the list</div>`)
    + `</article>`;
}

/* Paint the Shopping card. Header outside the card like every section; never blanks the
   column (a dead Mealie or a missing token gets a slim note). A repaint replaces the
   quick-add field, so carry its draft and focus/caret across (a refresh must not dismiss
   the on-screen keyboard mid-type) and the list's scroll position while it is in use. */
function renderShopping(s = shopData) {
  const host = document.getElementById('shopping-slot');
  if (!host) return;
  const listed = ((hubData && hubData.integrations) || []).some((i) => i.id === 'mealie');
  if (!listed && (s == null || !s.available)) { host.innerHTML = ''; return; }
  const items = shopItems(s);
  const open = s && Number.isInteger(s.open) ? s.open : items.filter((i) => !i.checked).length;
  const head = sectionHead('Shopping', open > 0 ? { chip: String(open) } : {});
  const body = s == null
    ? `<div class="card wx-loading" aria-hidden="true"></div>`
    : s.available
      ? shoppingCardHtml(items)
      : `<div class="wx-offline">${s.needs_auth ? 'Shopping needs a Mealie token' : 'Shopping unavailable'}</div>`;
  const prevInput = document.getElementById('shop-add-input');
  const draft = prevInput ? prevInput.value : '';
  const hadFocus = !!prevInput && document.activeElement === prevInput;
  const selStart = hadFocus ? prevInput.selectionStart : null;
  const selEnd = hadFocus ? prevInput.selectionEnd : null;
  const prev = typeof host.querySelector === 'function' ? host.querySelector('.shop-rows') : null;
  const keep = prev && prev.scrollTop > 0 && Date.now() - shopScrollAt < SHOP_SCROLL_KEEP_MS ? prev.scrollTop : 0;
  host.innerHTML = head + body;
  const inp = document.getElementById('shop-add-input');
  if (inp && draft) inp.value = draft;
  if (inp && hadFocus) {
    inp.focus();
    try { inp.setSelectionRange(selStart == null ? inp.value.length : selStart,
      selEnd == null ? inp.value.length : selEnd); } catch (e) { /* unsupported */ }
  }
  if (keep) {
    const next = host.querySelector('.shop-rows');
    if (next) next.scrollTop = keep;
  }
}

// scroll does not bubble: listen in the capture phase to learn when the list is being used
document.addEventListener('scroll', (e) => {
  const t = e.target;
  if (t && t.classList && t.classList.contains('shop-rows')) shopScrollAt = Date.now();
}, true);

async function fetchShopping() {
  // like fetchMeals: a hub that has loaded its registry and has no Mealie never asks
  const known = hubData && Array.isArray(hubData.integrations);
  if (known && !hubData.integrations.some((i) => i.id === 'mealie')) return;
  const seq = ++shopSeq;
  try {
    const s = await j('/api/mealie/shopping');
    if (seq !== shopSeq) return;
    shopData = s;
    shopFails = 0;
  } catch (e) {
    if (seq !== shopSeq) return;
    shopFails += 1;
    if (!shopData || shopFails >= TILE_FAIL_LIMIT) shopData = { available: false };
  }
  renderShopping();
}
```

- [ ] **Step 6: Wire the listing flip, bootstrap and poll** (`hub.js`)

In `renderIntegrations`, inside the existing `if (list.length && mealsListed !== mealsWasListed) { ... }` block, add (after `renderMeals();` and keeping the existing `if (mealsListed) fetchMeals();`):

```js
    if (!mealsListed) { shopData = null; shopFails = 0; }
    renderShopping();
    if (mealsListed) fetchShopping();
```

Next to `fetchMeals();` at the bootstrap (~line 5990) add `fetchShopping();`, and next to `setInterval(fetchMeals, POLL_MS);` add `setInterval(fetchShopping, POLL_MS);`.

- [ ] **Step 7: Add the CSS** (`styles.css`, directly after the `.meal-menu` rule block, ~line 1000)

```css
/* ---- native Shopping card: the Mealie list, scrolling INSIDE its card like the meal plan ---- */
.shopping-slot { min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.shop-card { padding: 0; overflow: hidden; min-width: 0; }
.shop-add { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--edge); }
.shop-add .txt-input { flex: 1; min-width: 0; }
/* The rows scroll INSIDE the card on the wall (the add field stays put above them), so a
   long list does not make the left column taller than the screen. The cap shows four rows
   and the top of the fifth: that peek is the hint there is more. The phone shell lifts it. */
.shop-rows { max-height: 200px; overflow-y: auto; overscroll-behavior: contain;
  scrollbar-width: thin; -webkit-overflow-scrolling: touch; }
.shop-row { display: flex; align-items: center; gap: 4px; padding: 0 12px 0 6px; min-height: 44px; min-width: 0;
  border-bottom: 1px solid var(--edge); }
.shop-row:last-child { border-bottom: 0; }
.shop-check { flex: none; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px;
  background: none; border: 0; padding: 0; cursor: pointer; color: inherit; }
.shop-row.done .todo-check { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
/* long names shrink to nothing and ellipsize (the same zero-basis trick as .meal-rname) */
.shop-text { flex: 1 1 0; width: 0; min-width: 0; text-align: left; background: none; border: 0; font: inherit;
  font-size: 14px; color: var(--ink); cursor: pointer; padding: 10px 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shop-row.done .shop-text { color: var(--dim); text-decoration: line-through; }
.shop-check:focus-visible, .shop-text:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }
/* a row's action menu, open inline under the row (a floating popover would be clipped by the scrolling list) */
.shop-menu { display: flex; gap: 8px; padding: 8px 14px 10px;
  background: color-mix(in srgb, var(--ink) 5%, transparent); border-bottom: 1px solid var(--edge); }
.shop-empty { padding: 16px 14px; font-size: 14px; color: var(--dim); }
```

And the hide hook beside the others (after the `body.integ-off-mealie #meals-slot` line, ~2386):

```css
body.integ-off-mealie #shopping-slot { display: none; }
```

- [ ] **Step 8: Run to verify they pass, then both full suites**

Run: `node --test tests/js/*.mjs` and `PYTHONPATH=src python -m pytest -q -p no:anyio`
Expected: all pass, including `test_css_braces_balanced`. If a static class guard names a class used in the new markup but undefined in CSS, define it (every class in `shoppingRowHtml`/`shoppingCardHtml` is defined above) rather than loosening the guard.

- [ ] **Step 9: Commit**

```bash
git add src/family_hub/web/static tests/js/hub-dom.test.mjs tests/test_static.py
git commit -m "feat(wall): Shopping card shows the Mealie list, scrolling inside its card"
```

---

### Task 5: Interactions (check, quick add, delete menu)

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (actions after `fetchShopping`; click/keydown/submit wiring ~4511, 4537-4540, 4720)
- Test: `tests/js/hub-dom.test.mjs`

**Interfaces:**
- Consumes: Task 4's state and renderers; `j`, `showToast`; the request contract from Task 3.
- Produces: `JSON_PUT(body)` helper; `shopCheck(id)`, `shopAdd()`, `shopDelete(id)`, `toggleShopMenu(id)`, `closeShopMenu(render = true)`.

- [ ] **Step 1: Write the failing tests** (append after Task 4's tests)

```js
const tapShop = (fire, host, sel) => {
  const btn = host.querySelector(sel);
  assert.ok(btn, `${sel} rendered`);
  const attr = sel.match(/\[(data-shop-[a-z]+)/)[1];
  btn.closest = (s) => (s === `[${attr}]` ? btn : null);
  fire('click', { target: btn, preventDefault() {} });
  return btn;
};

function shopSetup(list = SHOP_LIST(), opts = {}) {
  const hub = newHub();
  vm.runInContext(LISTED + `shopData = ${JSON.stringify(list)};`, hub.sandbox);
  const calls = shopFetchLog(hub.sandbox, { list, ...opts });
  hub.sandbox.renderShopping();
  return { ...hub, calls, host: hub.document.getElementById('shopping-slot') };
}

test('shopCheck: checks optimistically, PUTs checked:true, disables its own row meanwhile, re-reads', async () => {
  const { sandbox, fire, host, calls } = shopSetup();
  tapShop(fire, host, `[data-shop-check="${IID_A}"]`);
  assert.match(host.innerHTML, new RegExp(`shop-row done"><button[^>]*data-shop-check="${IID_A}"[^>]* disabled`), 'optimistic + busy');
  tapShop(fire, host, `[data-shop-check="${IID_A}"]`);            // a second tap while in flight is ignored
  await flush(); await flush();
  const puts = calls.filter((c) => c.method === 'PUT');
  assert.equal(puts.length, 1, 'one request, not two');
  assert.deepEqual(puts[0], { url: `/api/mealie/shopping/items/${IID_A}`, method: 'PUT', body: { checked: true } });
  assert.ok(calls.some((c) => c.url === '/api/mealie/shopping' && c.method === 'GET'), 'the list is re-read afterwards');
  assert.doesNotMatch(host.innerHTML, / disabled/, 'busy cleared');
});

test('shopCheck: a checked item un-checks (PUT checked:false)', async () => {
  const { fire, host, calls } = shopSetup();
  tapShop(fire, host, `[data-shop-check="${IID_C}"]`);
  await flush(); await flush();
  assert.deepEqual(calls.find((c) => c.method === 'PUT').body, { checked: false });
});

test('shopCheck: a refused write rolls the row back and shows the server reason', async () => {
  const { document, sandbox, fire, host } = shopSetup();
  sandbox.fetch = async (url, opts = {}) => (opts.method === 'PUT'
    ? { ok: false, status: 404, json: async () => ({ detail: 'that item is not on the list' }) }
    : { ok: true, status: 200, json: async () => ({ ...SHOP_LIST(), items: [shopItem(IID_B, 'Eggs')], open: 1 }) });
  tapShop(fire, host, `[data-shop-check="${IID_A}"]`);
  await flush(); await flush(); await flush();
  assert.equal(document.getElementById('toast').textContent, 'that item is not on the list');
  assert.doesNotMatch(host.innerHTML, new RegExp(IID_A), 'the re-read dropped the item Mealie no longer has');
});

test('shopAdd: posts the trimmed text once, clears the field, re-reads; blank text posts nothing', async () => {
  const { document, sandbox, calls } = shopSetup();
  const realInput = { value: '  Paper towels  ' };
  const orig = document.getElementById.bind(document);
  document.getElementById = (id) => (id === 'shop-add-input' ? realInput : orig(id));
  const first = sandbox.shopAdd();
  const second = sandbox.shopAdd();                      // an add while one is in flight is dropped
  await first; await second;
  assert.deepEqual(calls.filter((c) => c.method === 'POST').map((c) => c.body), [{ text: 'Paper towels' }]);
  assert.equal(realInput.value, '', 'the field is cleared');
  realInput.value = '   ';
  calls.length = 0;
  await sandbox.shopAdd();
  assert.equal(calls.filter((c) => c.method === 'POST').length, 0, 'blank text never posts');
});

test('shopAdd: a failed add keeps the text in the field and says why', async () => {
  const { document, sandbox } = shopSetup();
  const realInput = { value: 'Eggs' };
  const orig = document.getElementById.bind(document);
  document.getElementById = (id) => (id === 'shop-add-input' ? realInput : orig(id));
  sandbox.fetch = async (url, opts = {}) => (opts.method === 'POST'
    ? { ok: false, status: 502, json: async () => ({ detail: 'Mealie is unreachable' }) }
    : { ok: true, status: 200, json: async () => SHOP_LIST() });
  await sandbox.shopAdd();
  assert.equal(realInput.value, 'Eggs', 'nothing typed is lost');
  assert.equal(document.getElementById('toast').textContent, 'Mealie is unreachable');
});

test('the add form submits through the document submit handler (the on-screen keyboard Done path)', async () => {
  const { sandbox, fire, calls, document } = shopSetup();
  const realInput = { value: 'Milk' };
  const orig = document.getElementById.bind(document);
  document.getElementById = (id) => (id === 'shop-add-input' ? realInput : orig(id));
  let prevented = false;
  fire('submit', { target: { id: 'shop-add-form' }, preventDefault() { prevented = true; } });
  await flush(); await flush();
  assert.ok(prevented);
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { text: 'Milk' });
});

test('row menu: tapping the text opens an inline Delete; one menu at a time; closes on Escape and after an action', async () => {
  const { sandbox, fire, host, calls } = shopSetup();
  tapShop(fire, host, `[data-shop-open="${IID_A}"]`);
  assert.match(host.innerHTML, new RegExp(`class="shop-menu" id="shop-menu" role="group" aria-label="Actions for Milk"><button[^>]*data-shop-del="${IID_A}"`));
  assert.match(host.innerHTML, /aria-expanded="true" aria-controls="shop-menu"/);
  tapShop(fire, host, `[data-shop-open="${IID_B}"]`);                  // another row: the first closes
  assert.equal((host.innerHTML.match(/class="shop-menu"/g) || []).length, 1);
  assert.equal(vm.runInContext('shopMenuOpen', sandbox), IID_B);
  fire('keydown', { key: 'Escape' });
  assert.equal(vm.runInContext('shopMenuOpen', sandbox), null);
  assert.doesNotMatch(host.innerHTML, /class="shop-menu"/);
  tapShop(fire, host, `[data-shop-open="${IID_A}"]`);
  tapShop(fire, host, `[data-shop-del="${IID_A}"]`);
  await flush(); await flush();
  assert.deepEqual(calls.find((c) => c.method === 'DELETE'), { url: `/api/mealie/shopping/items/${IID_A}`, method: 'DELETE', body: null });
  assert.equal(vm.runInContext('shopMenuOpen', sandbox), null, 'the menu closes after the delete');
});

test('row menu: a tap anywhere else closes it (and still does what it was aimed at)', () => {
  const { sandbox, fire, host } = shopSetup();
  tapShop(fire, host, `[data-shop-open="${IID_A}"]`);
  fire('click', { target: { closest: () => null }, preventDefault() {} });
  assert.equal(vm.runInContext('shopMenuOpen', sandbox), null);
});

test('a write that fails keeps the last list instead of blanking the card', async () => {
  const { document, sandbox, fire, host } = shopSetup();
  sandbox.fetch = async (url, opts = {}) => (opts.method
    ? { ok: false, status: 502, json: async () => ({ detail: 'Mealie answered 500' }) }
    : { ok: false, status: 502, json: async () => ({ detail: 'down' }) });
  tapShop(fire, host, `[data-shop-check="${IID_A}"]`);
  await flush(); await flush(); await flush();
  assert.match(host.innerHTML, /data-shop-check/, 'one failed re-read does not blank the card');
  assert.equal(document.getElementById('toast').textContent, 'Mealie answered 500');
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/hub-dom.test.mjs`
Expected: FAIL (`sandbox.shopAdd is not a function`, taps do nothing).

- [ ] **Step 3: Implement the actions** (`hub.js`, directly after `fetchShopping`)

```js
const JSON_PUT = (body) => ({ method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) });

function shopItemById(id) {
  return shopData && Array.isArray(shopData.items) ? shopData.items.find((i) => i && i.id === id) : null;
}

/* Open/close a row's menu. One at a time; it closes by itself, on Escape, on a tap
   anywhere else (see the click handler) and after an action. */
function closeShopMenu(render = true) {
  clearTimeout(shopMenuTimer);
  shopMenuTimer = null;
  if (shopMenuOpen === null) return;
  shopMenuOpen = null;
  if (render) renderShopping();
}

function toggleShopMenu(id) {
  shopScrollAt = Date.now();      // any use of the list counts, not just a scroll: keep its place
  clearTimeout(shopMenuTimer);
  shopMenuTimer = null;
  shopMenuOpen = shopMenuOpen === id ? null : id;
  renderShopping();
  if (shopMenuOpen !== null) shopMenuTimer = setTimeout(closeShopMenu, SHOP_MENU_IDLE_MS);
}

document.addEventListener('keydown', (e) => {
  if (e && e.key === 'Escape' && shopMenuOpen !== null) closeShopMenu();
});

/* Check or un-check: shown at once (the list is a tap-and-go surface), PUT to the hub,
   rolled back with the server's reason if it refuses, and re-read either way so the card
   shows what Mealie actually has. A busy id ignores a second tap (no double toggle). */
async function shopCheck(id) {
  const it = shopItemById(id);
  if (!it || shopBusy.has(id)) return;
  const next = !it.checked;
  shopScrollAt = Date.now();
  shopBusy.add(id);
  it.checked = next;
  renderShopping();
  try {
    await j(`/api/mealie/shopping/items/${encodeURIComponent(id)}`, JSON_PUT({ checked: next }));
  } catch (e) {
    it.checked = !next;
    showToast((e && e.message) ? e.message : 'That did not work');
  } finally {
    shopBusy.delete(id);
    try { renderShopping(); } catch (e) { /* the re-read below repaints */ }
  }
  await fetchShopping();
}

async function shopAdd() {
  const input = document.getElementById('shop-add-input');
  const text = ((input && input.value) || '').trim();
  if (!text || shopAddBusy) return;
  shopAddBusy = true;
  try {
    await j('/api/mealie/shopping/items', JSON_POST({ text }));
    const now = document.getElementById('shop-add-input');
    if (now && now.value.trim() === text) now.value = '';   // never clear newer typing
  } catch (e) {
    showToast((e && e.message) ? e.message : 'That did not work');
  } finally {
    shopAddBusy = false;
  }
  await fetchShopping();
}

async function shopDelete(id) {
  if (shopBusy.has(id)) return;
  shopScrollAt = Date.now();
  shopBusy.add(id);
  closeShopMenu(false);
  try {
    renderShopping();
    await j(`/api/mealie/shopping/items/${encodeURIComponent(id)}`, { method: 'DELETE' });
  } catch (e) {
    showToast((e && e.message) ? e.message : 'That did not work');
  } finally {
    shopBusy.delete(id);
  }
  await fetchShopping();
}
```

- [ ] **Step 4: Wire the events** (`hub.js`)

In the document `click` handler, directly after the line that closes an open meal menu, add:

```js
  // a tap anywhere outside an open shopping row menu closes it (and still does what it was aimed at)
  if (shopMenuOpen !== null && !e.target.closest('.shop-menu') && !e.target.closest('[data-shop-open]')) closeShopMenu();
```

and directly after `if (mealBtnEl) { mealsAct(mealBtnEl); return; }`:

```js
  const shopCheckBtn = e.target.closest('[data-shop-check]');
  if (shopCheckBtn) { shopCheck(shopCheckBtn.dataset.shopCheck); return; }
  const shopOpenBtn = e.target.closest('[data-shop-open]');
  if (shopOpenBtn) { toggleShopMenu(shopOpenBtn.dataset.shopOpen); return; }
  const shopDelBtn = e.target.closest('[data-shop-del]');
  if (shopDelBtn) { shopDelete(shopDelBtn.dataset.shopDel); return; }
```

In the `submit` listener, add a second branch:

```js
  if (e.target && e.target.id === 'shop-add-form') {
    e.preventDefault();
    shopAdd();
  }
```

- [ ] **Step 5: Run to verify they pass, then both full suites**

Run: `node --test tests/js/*.mjs` and `PYTHONPATH=src python -m pytest -q -p no:anyio`
Expected: all pass. If a test that stubs `document.getElementById` leaks it into the next test, restore it in a `finally` (each test builds a fresh `newHub()`, so it should not).

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/web/static/hub.js tests/js/hub-dom.test.mjs
git commit -m "feat(wall): check, quick-add and delete on the Shopping card"
```

---

### Task 6: Wall layout reflow, wells, and the phone Meals tab

**Files:**
- Modify: `src/family_hub/web/static/hub.js` (`applyWallLayout`, ~1770-1800)
- Modify: `src/family_hub/web/static/styles.css` (wells ~2399, row gap ~2471, phone shell ~2541-2600)
- Test: `tests/test_static.py`

**Interfaces:**
- Consumes: Task 4's `#shopping-slot` and classes.
- Produces: `applyWallLayout` hides/shows `.shopping-slot` with the `mealie` integration and keeps `.col-left` alive when only Shopping is on; the phone shows `.shopping-slot` only on the Meals tab, after the Dinner card.

- [ ] **Step 1: Write the failing static guards** (`tests/test_static.py`, after Task 4's guards)

```python
def test_shopping_phone_rules_show_it_on_the_meals_tab_only_and_lift_the_scroll_cap():
    """On the phone .col-left is display:contents, so the Shopping slot is a direct flex
    child of the shell: hidden everywhere by default, shown (after the Dinner card, via
    order) on the Meals tab; the list lifts its wall height cap (the tab is its own
    scrolling page) and its controls are full-size tap targets."""
    mobile = _phone_shell_css()
    assert re.search(r'\.shopping-slot\s*\{[^}]*display:\s*none', mobile), \
        "hidden on every phone tab by default (the To-Do slot is hidden the same way)"
    assert re.search(r'body\[data-tab="meals"\] \.shopping-slot\s*\{[^}]*display:\s*flex[^}]*order:\s*\d', mobile), \
        "shown on the Meals tab, ordered after the Dinner card"
    assert re.search(r'\.shop-rows\s*\{\s*max-height:\s*none;\s*overflow:\s*visible', mobile), \
        "the phone must show the whole list, not a small scroller inside a scrolling page"
    assert re.search(r'\.shop-row\s*\{\s*min-height:\s*52px', mobile), "phone rows are comfortably tappable"
    assert re.search(r'\.shop-check\s*\{[^}]*width:\s*48px', mobile) or re.search(r'\.shop-check\s*\{[^}]*min-height:\s*44px', mobile)


def test_shopping_slot_follows_the_wells_and_gap_rules_of_its_neighbour_the_todo_slot():
    assert re.search(r':root\[data-cols="wells"\] \.shopping-slot', CSS), \
        "in the 'wells' look the Shopping card gets the same tinted panel as the To-Do slot"
    assert re.search(r'(?m)^\s*\.shopping-slot,\s*\.todo-slot\s*\{\s*gap:\s*10px|\.todo-slot,\s*\.shopping-slot\s*\{\s*gap:\s*10px', CSS)


def test_applywalllayout_keeps_the_left_column_alive_for_shopping_alone():
    hub = (STATIC / "hub.js").read_text()
    body = hub[hub.index("function applyWallLayout"):]
    body = body[:body.index("\n}\n")]
    assert re.search(r"const shopping = has\('mealie'\)", body)
    assert re.search(r"setDisp\('\.col-left', chores \|\| todos \|\| shopping\)", body), \
        "with Chores and To-Dos both off, Shopping alone must still show the left column"
    assert "setDisp('.shopping-slot', shopping)" in body
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_static.py -q -p no:anyio -k "shopping or applywalllayout"`
Expected: FAIL.

- [ ] **Step 3: Implement the reflow** (`hub.js`, inside `applyWallLayout`)

Add after `const cameras = has('cameras');`:

```js
  const shopping = has('mealie');
```
and change the two `setDisp` lines:

```js
  setDisp('.todo-slot', todos);
  setDisp('.shopping-slot', shopping);
  setDisp('.col-left', chores || todos || shopping);
```

- [ ] **Step 4: Implement the CSS**

Wells (add `.shopping-slot` to the existing group, after `.todo-slot`):

```css
:root[data-cols="wells"] .todo-slot,
:root[data-cols="wells"] .shopping-slot,
```

Gap (the rule inside the existing media block at ~2471):

```css
  .todo-slot, .shopping-slot { gap: 10px; }
```
(replace the single `.todo-slot { gap: 10px; }` line.)

Phone shell: directly after the existing `:root:not([data-layout="desktop"]) .todo-slot { display: none; }` line (~2541):

```css
  :root:not([data-layout="desktop"]) .shopping-slot { display: none; }
```
and after the `.meal-photo` phone rule (~2603), keeping everything inside the phone-shell markers:

```css
  /* the Shopping card is a section of the Meals tab: .col-left is display:contents here,
     so the slot is a direct child of the shell's flex column; order puts it after .panels
     (the Dinner card). The list lifts its wall height cap, and every control is full size. */
  :root:not([data-layout="desktop"]) body[data-tab="meals"] .shopping-slot { display: flex; order: 2; }
  :root:not([data-layout="desktop"]) .shop-rows { max-height: none; overflow: visible; }
  :root:not([data-layout="desktop"]) .shop-row { min-height: 52px; }
  :root:not([data-layout="desktop"]) .shop-check { width: 48px; min-height: 44px; }
  :root:not([data-layout="desktop"]) .shop-text { font-size: 15px; }
  :root:not([data-layout="desktop"]) .shop-menu .meal-btn { min-height: 44px; }
```
Also add `.shopping-slot` to the other tabs' hide lists only if the manual phone check (Task 7) shows it leaking: the default `display: none` above plus the Meals-tab-only `display: flex` already covers every tab, because the Meals rule has higher specificity than the default hide.

- [ ] **Step 5: Run to verify they pass, then both full suites**

Run: `PYTHONPATH=src python -m pytest -q -p no:anyio` and `node --test tests/js/*.mjs`
Expected: all pass, including `test_css_braces_balanced`, the phone-shell marker/brace guards, and the tab-surface guards.

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/web/static/hub.js src/family_hub/web/static/styles.css tests/test_static.py
git commit -m "feat(wall): Shopping reflows with To-Dos, joins the wells look, and lives on the phone Meals tab"
```

---

### Task 7: Visual gates, docs, screenshot, review (the repo's gauntlet)

This is the part `docs/adding-a-feature.md` says a green suite cannot see. It needs a real browser, so it is a checklist with the exact commands; do not skip any line.

**Files:**
- Modify: `README.md`, `docs/hub.png`, `CHANGELOG.md`

- [ ] **Step 1: Run the demo and look at it**

```bash
cd C:/Users/mrtim/Documents/family-hub
DEMO=1 DISABLE_SYNC=1 CONFIG_PATH=config.demo.json python -m uvicorn family_hub.app:app --app-dir src --port 8199
```
Open `http://127.0.0.1:8199/` in a real browser (clear the browser cache first, `Network.clearBrowserCache`, since asset `?v=` is unchanged between releases). Check each of the following and fix what you find (each fix gets the guard that would have caught it):
  - Full-width wall (>= 1920 px): the Shopping card sits under Chores beside To-Dos; the list shows about four rows and a peek and scrolls inside the card; the quick-add stays put while scrolling; tap/click an item to check it (in demo the write is a no-op, so it reverts on the next read, which is expected).
  - **To-Dos off** (Settings -> To-Dos switch): Shopping takes the space, nothing overflows. **Meals (Mealie) off:** Shopping hides and the column reflows. **Chores and To-Dos both off with Mealie on:** the left column still shows Shopping.
  - All five themes (Light, Soft, Blue, Grey, Black); the "wells" and "lines" column looks; night mode (`.is-night`); seasons off and on (check glass in Chromium, since Firefox screenshots skip `backdrop-filter`); the gear popover opens over the card, not under it.
  - Phone width at 390 px and 360 px and <= 400 px (use the CLAUDE.md temporary `@media (max-width: 2000px)` trick, then REVERT it): the Meals tab shows Dinner then Shopping; no other tab shows Shopping; no horizontal overflow with a long item name and the clock at 12:59:59pm; tap targets are >= 44 px.
  - Long list (edit the demo payload locally to ~60 items): the page does not grow, the chip shows the open count; empty list shows "Nothing on the list"; stop the demo's Mealie (set `DEMO` off with a bogus config) to see the unavailable note.
- [ ] **Step 2: Anything the feature can switch off must not move a pixel when off.** Screenshot the wall with Mealie off on `main` and on this branch, all five themes, and diff them.
- [ ] **Step 3: README.** Add a Shopping bullet to "What it looks like", mention the Shopping list in the Meals/Mealie section, and note that `mealie.shopping_list` also picks the list the card shows.
- [ ] **Step 4: Regenerate `docs/hub.png`** from the demo at 1920 px wide, full page, with the Shopping card showing its best state (open items, a couple checked, list scrolled to the top). `docs/phone.png` is unchanged unless the phone home screen changed (it did not).
- [ ] **Step 5: Run both suites under `TZ=UTC` and with the repo's pre-push privacy guard**

```bash
TZ=UTC PYTHONPATH=src python -m pytest -q -p no:anyio
TZ=UTC node --test tests/js/*.mjs
bash scripts/install-hooks.sh
```
Expected: all pass; confirm no test was skipped (`-ra` prints skips).
- [ ] **Step 6: Review gate.** Run the three review agents on the branch diff (`pr-review-toolkit:silent-failure-hunter`, `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:pr-test-analyzer`), fix every real finding (each with its guard), and re-run if the branch grew afterwards.
- [ ] **Step 7: Changelog check.** Confirm the `### Added` entry from Task 3 mentions the phone section and, if Task 0 showed Mealie drops `recipeReferences` on update, add a `### Known limits` sentence saying checking a recipe-derived item can detach it from its recipe in Mealie (display is unaffected).
- [ ] **Step 8: Commit and push the branch, open the PR**

```bash
git add README.md docs/hub.png CHANGELOG.md
git commit -m "docs: Shopping card in the README and hub.png"
git push -u origin feat/shopping-card
```
Open the PR to `dapperdodger/family-hub` `main` with the Task 0 probe results, the screenshots, and the checklist above, ending with the two PR attribution lines. (The operator merges.)

---

### Task 8: Pi kiosk, the on-screen keyboard and the live check (operator-run)

Separate repo (`family-hub-deploy`) plus the operator's real hardware. The wall's keyboard only turns on when the page was opened once with `?kiosk=1`; the Pi kiosk service does not pass it, so quick add would have no keyboard on the fridge screen.

**Files:**
- Modify (in `family-hub-deploy`): `pi-kiosk/setup-kiosk.sh`, `pi-kiosk/README.md`

- [ ] **Step 1: Default the kiosk URL to the keyboard-enabled one.** In `pi-kiosk/setup-kiosk.sh` change `URL="${1:-http://192.168.1.50:8138}"` to `URL="${1:-http://192.168.1.50:8138/?kiosk=1}"`. In `pi-kiosk/README.md`, note that `?kiosk=1` latches the hub's on-screen keyboard (osk.js) so tapping the Shopping quick-add or a To-Do field summons it, and that `?kiosk=0` clears it.
- [ ] **Step 2: On the Pi, apply it without re-running everything.** Edit `/etc/systemd/system/kiosk.service`, append `?kiosk=1` to the URL on the last `ExecStart` line, then `sudo systemctl daemon-reload && sudo systemctl restart kiosk`.
- [ ] **Step 3: After the PR is merged and the new image is deployed** (Actions publishes `ghcr.io/dapperdodger/family-hub` on merge; update the `family-hub` app on TrueNAS), verify live:
  - `curl http://192.168.1.50:8138/api/mealie/shopping` returns `{"available": true, ...}` with your real list.
  - On the wall: the card shows the real list; tap an item and it checks in Mealie (open Mealie to confirm, then un-check it); quick add on the touchscreen summons the on-screen keyboard and the item appears in Mealie; delete removes it; the wall reaches zero console errors.
  - On the Pi 3: the card paints and scrolls without lag (the hub poll interval is 60 s, so a smooth tap-to-check is the real test); `vcgencmd get_throttled` stays `0x0`.
  - On a real iPhone: the Meals tab shows Dinner then Shopping, checking and adding work, no sideways scroll.
- [ ] **Step 4: Commit in `family-hub-deploy`:** `git add pi-kiosk && git commit -m "pi-kiosk: open the hub with ?kiosk=1 so the on-screen keyboard works" && git push origin main`.
- [ ] **Step 5: Clean up.** Stop the demo server, delete scratch screenshots and the probe script, and delete the merged branch.

---

## Self-review (run against the spec)

- **Scope / backend (read, add, check, delete, list-membership, lock, demo, health):** Tasks 1-3. The `health` line in the spec is satisfied by *not* adding a source: the card rides `meals`, and Task 1 has a test that a failing shopping read leaves the dinner source's state alone.
- **Scroll like the meal plan (user request):** Task 4 CSS + `test_shopping_list_scrolls_inside_its_card_on_the_wall`, Task 4's repaint keeps scroll, Task 6 phone lift + guard.
- **Row menu inline, one tap check / two tap delete:** Task 5.
- **Placement, To-Dos on/off, reflow:** Task 4 (hide hook), Task 6 (`applyWallLayout`, wells, phone), Task 7 visual gates.
- **Phone Meals-tab section:** Task 6.
- **Optimistic check + rollback, newest-wins, focus/scroll carry, failure states, empty state:** Tasks 4-5.
- **Motion:** no animation added; the check reuses `.todo-check` without `check-pop`.
- **Open items from the spec:** list read endpoint (`GET /shopping/lists/{id}` returns `listItems`) decided in Task 1; display-vs-note decided in `_shopping_item`; row budget 200 px set in Task 4 and tuned in Task 7; To-Dos-off layout verified in Task 6/7; Pi 3 measured in Task 8.
- **Placeholder scan:** none; the only operator-supplied values are the real token (Task 0) and live checks (Task 8).
- **Type consistency:** `shopping_tile`/`add_shopping_item`/`set_shopping_checked`/`delete_shopping_item` (Tasks 1-3), the JSON shapes `{id,text,checked}` + `open` (Tasks 1, 3, 4), `data-shop-check/open/del` -> `dataset.shopCheck/shopOpen/shopDel` (Tasks 4-5), `shopMenuOpen`/`shopBusy`/`shopAddBusy` (Tasks 4-5) all match.
