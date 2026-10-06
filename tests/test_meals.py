"""The Meals card's backend: config cleaning, the registry entry, the fail-soft
Mealie read, the three writes (random dinner / re-roll, add to shopping list),
the photo proxy, and the routes (including the persisted re-roll safety)."""
import asyncio
import datetime as dt
import importlib
import json
import logging
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from family_hub import integrations, meals, tiles
from family_hub import tiles as ftiles
from family_hub.config import Config, _clean_mealie

TODAY = dt.date(2026, 10, 1)
RID = "08481e68-b32a-45db-9f99-f036126dba27"
RID2 = "9cc3dd7f-6004-48f8-b70a-188022e816b9"
ENV = {"MEALIE_API_TOKEN": "tok"}
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


def recipe(slug, name=None, rid=RID, **kw):
    """A recipe summary as Mealie's /api/recipes returns it."""
    r = {"id": rid, "slug": slug, "name": name or slug.replace("-", " ").title(), "image": "abc",
         "totalTime": "30 Minutes",
         "recipeCategory": [{"id": "c1", "name": "Dinner", "slug": "dinner"}],
         "tags": [{"id": "t1", "name": "Easy", "slug": "easy"}],
         "rating": 4, "dateAdded": "2026-09-01T10:00:00+00:00", "lastMade": None}
    r.update(kw)
    return r


def mcfg(**over):
    block = {"base": "http://mealie", "days": 5}
    block.update(over)
    return Config(mealie=block)


def entry(eid, day, name="Baked Ziti", rid=RID, image="abc", **kw):
    e = {"id": eid, "date": day, "entryType": "dinner", "title": "", "text": "",
         "recipeId": rid, "recipe": {"id": rid, "name": name,
                                     "description": f"About {name}.", "image": image}}
    e.update(kw)
    return e


def d(n):
    return (TODAY + dt.timedelta(days=n)).isoformat()


def roll(eid, n, rid=RID):
    """A rolled-map entry: the hub picked recipe `rid` for entry `eid` on day n."""
    return {eid: (rid, d(n))}


class FakeMealie:
    """A tiny Mealie: a plan, shopping lists, and a log of every request."""

    def __init__(self, plan=None, lists=None, items=None, recipes=None, details=None):
        self.plan = list(plan or [])
        self.lists = lists if lists is not None else [{"id": RID2, "name": "Groceries"}]
        self.items = list(items or [])
        self.recipes = list(recipes or [])
        self.details = dict(details or {})
        self.missing_files = set()     # media file names that 404
        self.log = []
        self.fail = {}          # (METHOD, path-prefix) -> status
        self.next_id = 100
        self.calls = []         # {"method", "path", "params", "body"} for every request

    def handler(self, req):
        self.log.append((req.method, req.url.path))
        self.calls.append({"method": req.method, "path": req.url.path, "params": dict(req.url.params),
                           "body": json.loads(req.content) if req.content else None})
        for (m, prefix), status in self.fail.items():
            if req.method == m and req.url.path.startswith(prefix):
                return httpx.Response(status, json={"detail": "x"})
        p = req.url.path
        if req.headers.get("authorization") != "Bearer tok":
            return httpx.Response(401, json={"detail": "no"})
        if req.method == "GET" and p == "/api/households/mealplans":
            q = req.url.params
            lo, hi = q["start_date"], q["end_date"]
            return httpx.Response(200, json={"items": [
                e for e in self.plan
                if not isinstance(e.get("date"), str) or lo <= e["date"] <= hi]})
        if req.method == "POST" and p == "/api/households/mealplans/random":
            body = json.loads(req.content)
            self.next_id += 1
            new = entry(self.next_id, body["date"], name=f"Random {self.next_id}")
            self.plan.append(new)
            return httpx.Response(200, json=new)
        if req.method == "DELETE" and p.startswith("/api/households/mealplans/"):
            eid = int(p.rsplit("/", 1)[1])
            if not any(e["id"] == eid for e in self.plan):
                return httpx.Response(404, json={"detail": "not found"})
            self.plan = [e for e in self.plan if e["id"] != eid]
            return httpx.Response(200, json={})
        if req.method == "GET" and p == "/api/households/shopping/lists":
            return httpx.Response(200, json={"items": self.lists})
        if req.method == "POST" and "/shopping/lists/" in p and p.endswith(f"/recipe/{RID}"):
            return httpx.Response(200, json={})
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
        return httpx.Response(404)


def run(fake, coro_fn, cfg=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            return await coro_fn(c, cfg or mcfg())
    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _fresh():
    tiles.reset_caches()
    yield
    tiles.reset_caches()


# ------------------------------------------------------------- config cleaning

def test_clean_mealie_keeps_a_good_block_and_strips_the_trailing_slash():
    assert _clean_mealie({"base": "http://m:9000/"}) == {"base": "http://m:9000", "days": 5}
    out = _clean_mealie({"base": "https://m", "days": 4, "open_url": "http://lan:9000/",
                         "shopping_list": " Groceries "})
    assert out == {"base": "https://m", "days": 4, "open_url": "http://lan:9000",
                   "shopping_list": "Groceries"}


@pytest.mark.parametrize("raw", [None])
def test_clean_mealie_absent_is_simply_off(raw):
    assert _clean_mealie(raw) is None


@pytest.mark.parametrize("raw", [{}, {"base": ""}, {"base": "ftp://x"}, {"base": "mealie:9000"},
                                 "http://m", [], 5, {"days": 4}])
def test_clean_mealie_malformed_is_dropped_loudly(raw, caplog):
    with caplog.at_level(logging.WARNING, logger="family_hub.config"):
        assert _clean_mealie(raw) is None
    assert "mealie" in caplog.text and "OFF" in caplog.text


@pytest.mark.parametrize("days,want", [(1, 3), (3, 3), (7, 7), (30, 7), (-2, 3)])
def test_clean_mealie_clamps_days(days, want):
    assert _clean_mealie({"base": "http://m", "days": days})["days"] == want


@pytest.mark.parametrize("days", ["4", 4.5, True, [], {}])
def test_clean_mealie_ignores_a_non_integer_days(days):
    assert _clean_mealie({"base": "http://m", "days": days})["days"] == 5


def test_clean_mealie_drops_a_bad_open_url_and_blank_list():
    out = _clean_mealie({"base": "http://m", "open_url": "javascript:alert(1)", "shopping_list": "  "})
    assert out == {"base": "http://m", "days": 5}


# -------------------------------------------------------------------- registry

def test_registry_lists_meals_iff_configured_and_a_missing_token_stays_listed():
    off = {i["id"]: i for i in integrations.available_integrations(Config(), {})}
    on = {i["id"]: i for i in integrations.available_integrations(mcfg(), {})}
    assert off["mealie"]["available"] is False
    assert on["mealie"]["available"] is True and on["mealie"]["group"] == "integration"
    assert integrations.mealie_token({"MEALIE_API_TOKEN": "   "}) == ""
    assert integrations.mealie_token({"MEALIE_API_TOKEN": " t "}) == "t"


# ------------------------------------------------------------------ the read

def test_tile_happy_shape_and_empty_days():
    fake = FakeMealie([entry(1, d(0)), entry(2, d(2), name="Soup", rid=RID2, image=None)])
    t = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))
    assert t["available"] is True and t["open_url"] == "http://mealie"
    assert [x["date"] for x in t["days"]] == [d(i) for i in range(5)]
    assert t["days"][0]["dinner"] == {
        "id": 1, "recipe_id": RID, "name": "Baked Ziti", "description": "About Baked Ziti.",
        "has_image": True, "rolled": False, "more": 0}
    assert t["days"][1]["dinner"] is None
    assert t["days"][2]["dinner"]["has_image"] is False
    assert t["days"][3]["dinner"] is None


def test_tile_ignores_other_meal_types_and_names_an_unnamed_dinner():
    fake = FakeMealie([entry(1, d(0), entryType="lunch"),
                       {"id": 2, "date": d(0), "entryType": "dinner", "title": "", "recipe": None},
                       {"id": 3, "date": d(1), "entryType": "dinner", "title": "Leftovers", "recipe": None}])
    t = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))
    assert t["days"][0]["dinner"]["name"] == "Dinner planned", "the unnamed dinner occupies the day; the lunch is ignored"
    assert t["days"][1]["dinner"]["name"] == "Leftovers"
    assert t["days"][1]["dinner"]["recipe_id"] is None


def test_tile_reports_extra_dinners_on_a_day_and_shows_the_first():
    fake = FakeMealie([entry(5, d(0), name="Second"), entry(2, d(0), name="First")])
    dn = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))["days"][0]["dinner"]
    assert dn["name"] == "First" and dn["more"] == 1


def test_tile_truncates_long_text():
    fake = FakeMealie([entry(1, d(0), name="N" * 500)])
    fake.plan[0]["recipe"]["description"] = "D" * 900
    dn = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))["days"][0]["dinner"]
    assert len(dn["name"]) == 120 and len(dn["description"]) == meals.DESCRIPTION_MAX


@pytest.mark.parametrize("body", [None, [], "x", 5, {}, {"items": None}, {"items": "no"},
                                  {"items": [None, 5, "x", []]}])
def test_tile_never_raises_on_a_wrong_shaped_body(body):
    def handler(req):
        return httpx.Response(200, json=body)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.meals_tile(c, mcfg(), ENV, TODAY)
    t = asyncio.run(go())
    # a body with no items list is unavailable; a list of junk items is just empty days
    assert t["available"] is bool(isinstance(body, dict) and isinstance(body.get("items"), list))
    if t["available"]:
        assert all(day["dinner"] is None for day in t["days"])


def test_tile_survives_wrong_typed_fields_inside_entries():
    junk = [{"id": True, "date": d(0), "entryType": "dinner", "recipe": {"name": 5, "id": 7, "image": []},
             "title": 9},
            {"id": "x", "date": 5, "entryType": "dinner", "recipe": "nope"},
            {"id": 3, "date": d(1), "entryType": "dinner", "recipe": {"name": "Ok", "id": "not-a-uuid"}}]
    t = run(FakeMealie(junk), lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))
    assert t["available"] is True
    assert t["days"][0]["dinner"]["name"] == "Dinner planned", "wrong-typed name/title still OCCUPY the day"
    ok = t["days"][1]["dinner"]
    assert ok["name"] == "Ok" and ok["recipe_id"] is None and ok["has_image"] is False


def test_tile_without_a_token_is_listed_as_needs_auth_and_makes_no_request():
    fake = FakeMealie([entry(1, d(0))])
    t = run(fake, lambda c, cf: meals.meals_tile(c, cf, {}, TODAY))
    assert t == {"available": False, "needs_auth": True}
    assert fake.log == []
    assert "MEALIE_API_TOKEN" in tiles.SOURCE_STATE["meals"]["last_error"]


@pytest.mark.parametrize("status,auth", [(401, True), (403, True), (500, False), (404, False)])
def test_tile_upstream_errors_are_unavailable_and_flag_auth_only_for_401_403(status, auth):
    fake = FakeMealie()
    fake.fail[("GET", "/api/households/mealplans")] = status
    t = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))
    assert t == {"available": False, "needs_auth": auth}


def test_tile_transport_error_is_unavailable_never_cached():
    calls = []
    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"items": []})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            a = await meals.meals_tile(c, mcfg(), ENV, TODAY)
            b = await meals.meals_tile(c, mcfg(), ENV, TODAY)
            return a, b
    a, b = asyncio.run(go())
    assert a["available"] is False and b["available"] is True, "the failure was not cached"
    assert tiles.SOURCE_STATE["meals"].get("last_error") is None, "a good read clears the error"


def test_tile_is_cached_briefly_and_rolled_flags_follow_the_live_set():
    fake = FakeMealie([entry(1, d(0))])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            a = await meals.meals_tile(c, mcfg(), ENV, TODAY, {})
            b = await meals.meals_tile(c, mcfg(), ENV, TODAY, roll(1, 0))
            return a, b
    a, b = asyncio.run(go())
    assert len(fake.log) == 1, "second read came from the cache"
    assert a["days"][0]["dinner"]["rolled"] is False
    assert b["days"][0]["dinner"]["rolled"] is True, "rolled is recomputed, not cached"


# ------------------------------------------------------------ random + re-roll

def test_random_plans_an_empty_day():
    fake = FakeMealie([entry(1, d(0))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(2), TODAY, {}))
    assert r["ok"] is True and isinstance(r["entry_id"], int)
    assert any(e["date"] == d(2) for e in fake.plan)


def test_random_refuses_a_day_that_already_has_a_dinner():
    fake = FakeMealie([entry(1, d(0))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(0), TODAY, {}))
    assert r["ok"] is False and r["status"] == 409
    assert ("POST", "/api/households/mealplans/random") not in fake.log


@pytest.mark.parametrize("date", [d(-1), d(5), d(40), "2026-13-01", "nope", "", None, 5, "2026-10-1"])
def test_random_rejects_dates_outside_the_planned_days(date):
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, date, TODAY, {}))
    assert r["ok"] is False and r["status"] == 422 and fake.log == []


def test_reroll_replaces_only_a_dinner_this_hub_picked_new_first_then_delete():
    fake = FakeMealie([entry(7, d(1))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is True
    assert [e["id"] for e in fake.plan] == [r["entry_id"]]
    posts = [i for i, (m, p) in enumerate(fake.log) if p.endswith("/random")]
    dels = [i for i, (m, p) in enumerate(fake.log) if m == "DELETE"]
    assert posts and dels and posts[0] < dels[0], "the new pick is made BEFORE the old one goes"


@pytest.mark.parametrize("replace_id", [7, "7", True, 1.0, -1])
def test_reroll_of_a_dinner_not_in_the_rolled_set_is_refused(replace_id):
    fake = FakeMealie([entry(7, d(1))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {}, replace_id=replace_id))
    assert r["ok"] is False and r["status"] == 409
    assert [e["id"] for e in fake.plan] == [7], "a hand-planned dinner is never replaced"
    assert not any(m == "DELETE" for m, _ in fake.log)


def test_reroll_draws_again_when_it_lands_on_the_same_recipe():
    fake = FakeMealie([entry(7, d(1), rid=RID)])
    picks = iter([RID, RID, RID2])           # same, same, then a different recipe
    orig = fake.handler
    def handler(req):
        if req.method == "POST" and req.url.path.endswith("/random"):
            fake.next_id += 1
            new = entry(fake.next_id, json.loads(req.content)["date"], rid=next(picks))
            fake.plan.append(new)
            fake.log.append((req.method, req.url.path))
            return httpx.Response(200, json=new)
        return orig(req)
    fake.handler = handler
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is True
    assert [e["recipeId"] for e in fake.plan] == [RID2], "one dinner left, and it is a different recipe"
    assert sum(1 for m, p in fake.log if p.endswith("/random")) == 3


def test_reroll_gives_up_after_a_few_tries_and_keeps_the_last_pick():
    fake = FakeMealie([entry(7, d(1), rid=RID)])
    orig = fake.handler
    def handler(req):
        if req.method == "POST" and req.url.path.endswith("/random"):
            fake.next_id += 1
            new = entry(fake.next_id, json.loads(req.content)["date"], rid=RID)   # always the same
            fake.plan.append(new)
            fake.log.append((req.method, req.url.path))
            return httpx.Response(200, json=new)
        return orig(req)
    fake.handler = handler
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is True and len(fake.plan) == 1, "never loops forever, never leaves two dinners"
    assert sum(1 for m, p in fake.log if p.endswith("/random")) == meals.RANDOM_TRIES


def test_reroll_of_a_dinner_that_vanished_is_a_409_not_a_blind_delete():
    fake = FakeMealie([])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is False and r["status"] == 409
    assert fake.log and not any(m in ("DELETE",) or p.endswith("/random") for m, p in fake.log)


def test_reroll_that_cannot_remove_the_old_dinner_undoes_the_new_pick():
    fake = FakeMealie([entry(7, d(1))])
    fake.fail[("DELETE", "/api/households/mealplans/7")] = 500
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is False and r["status"] == 502
    assert [e["id"] for e in fake.plan] == [7], "the day still shows exactly the old dinner"


def test_random_upstream_failure_is_a_502_with_a_reason_and_no_delete():
    fake = FakeMealie([entry(7, d(1))])
    fake.fail[("POST", "/api/households/mealplans/random")] = 500
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is False and r["status"] == 502 and "Mealie" in r["error"]
    assert [e["id"] for e in fake.plan] == [7]


def test_random_with_a_malformed_reply_fails_cleanly():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json={"no": "id"})
        return httpx.Response(200, json={"items": []})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.random_dinner(c, mcfg(), ENV, d(1), TODAY, {})
    r = asyncio.run(go())
    assert r["ok"] is False and r["status"] == 502


def test_writes_without_a_token_or_config_are_refused_without_a_request():
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, {}, d(1), TODAY, {}))
    assert r["ok"] is False and r["status"] == 503 and r["needs_auth"] is True
    r = run(fake, lambda c, cf: meals.random_dinner(c, Config(), ENV, d(1), TODAY, {}))
    assert r["ok"] is False and r["status"] == 404
    assert fake.log == []


# --------------------------------------------------------------------- shopping

def test_shopping_uses_the_first_list_by_default():
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID))
    assert r == {"ok": True, "list": "Groceries"}
    assert ("POST", f"/api/households/shopping/lists/{RID2}/recipe/{RID}") in fake.log


@pytest.mark.parametrize("want", ["Weekly", "weekly", RID])
def test_shopping_honors_a_configured_list_by_name_or_id(want):
    other = "11111111-1111-1111-1111-111111111111"
    fake = FakeMealie(lists=[{"id": RID2, "name": "Groceries"}, {"id": other, "name": "Weekly"},
                             {"id": RID, "name": "ById"}])
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID), mcfg(shopping_list=want))
    assert r["ok"] is True
    target = RID if want == RID else other
    assert any(p.startswith(f"/api/households/shopping/lists/{target}/recipe/") for _, p in fake.log)


def test_shopping_with_no_matching_or_no_list_is_a_409_with_a_reason():
    r = run(FakeMealie(lists=[]), lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID))
    assert r["ok"] is False and r["status"] == 409 and "no shopping list" in r["error"].lower()
    r = run(FakeMealie(), lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID), mcfg(shopping_list="Nope"))
    assert r["ok"] is False and r["status"] == 409


@pytest.mark.parametrize("rid", ["../../etc/passwd", "x", "", None, 5, RID + "/../x", "a" * 36 + "?"])
def test_shopping_rejects_a_recipe_id_that_is_not_a_uuid_before_any_request(rid):
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, rid))
    assert r["ok"] is False and r["status"] == 422 and fake.log == []


def test_shopping_upstream_failure_is_a_502():
    fake = FakeMealie()
    fake.fail[("POST", "/api/households/shopping/lists/")] = 500
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID))
    assert r["ok"] is False and r["status"] == 502


# ------------------------------------------------------------------------ image

def test_image_proxy_returns_bytes_caches_and_rejects_non_images_and_bad_ids():
    fake = FakeMealie()
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            a = await meals.fetch_image(c, mcfg(), ENV, RID)
            b = await meals.fetch_image(c, mcfg(), ENV, RID)
            bad = await meals.fetch_image(c, mcfg(), ENV, "../x")
            return a, b, bad
    a, b, bad = asyncio.run(go())
    assert a == (b"IMG", "image/webp") and a == b and bad is None
    assert len([1 for m, p in fake.log if p.startswith("/api/media/")]) == 1, "cached"

    def html(req):
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    async def go2():
        async with httpx.AsyncClient(transport=httpx.MockTransport(html)) as c:
            return await meals.fetch_image(c, mcfg(), ENV, RID2)
    assert asyncio.run(go2()) is None, "never relay a non-image body"


def test_image_cache_is_bounded():
    fake = FakeMealie()
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            for n in range(meals.IMAGE_CACHE_MAX + 5):
                await meals.fetch_image(c, mcfg(), ENV, f"{n:036d}")
    asyncio.run(go())
    assert len(meals._image_cache) <= meals.IMAGE_CACHE_MAX


# ----------------------------------------------------------------------- routes

def _write_cfg(tmp_path, mealie=True):
    block = {"mealie": {"base": "http://mealie", "days": 5}} if mealie else {}
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"port": 8138, "calendars": [], **block}))
    return str(p)


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "hub.db"))
    monkeypatch.setenv("TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("DISABLE_SYNC", "1")
    monkeypatch.setenv("MEALIE_API_TOKEN", "tok")
    monkeypatch.setenv("CONFIG_PATH", _write_cfg(tmp_path))
    import family_hub.app as appmod
    importlib.reload(appmod)
    fake = FakeMealie()
    appmod._http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(appmod, "_today", lambda: TODAY)
    with TestClient(appmod.app) as c:
        yield appmod, c, fake


def test_route_tile_reads_the_plan(app_env):
    appmod, c, fake = app_env
    fake.plan.append(entry(1, d(0)))
    t = c.get("/api/tiles/mealie").json()
    assert t["available"] is True and t["days"][0]["dinner"]["name"] == "Baked Ziti"


def test_route_random_persists_the_pick_so_it_can_be_rerolled_after_a_restart(app_env):
    appmod, c, fake = app_env
    r = c.post("/api/mealie/random", json={"date": d(1)})
    assert r.status_code == 200
    eid = r.json()["entry_id"]
    assert appmod._meals_rolled() == {eid: (r.json()["recipe_id"], d(1))}
    t = c.get("/api/tiles/mealie").json()
    assert t["days"][1]["dinner"]["rolled"] is True, "the card is told it may re-roll this one"
    # re-roll swaps the remembered id, so only the NEW pick stays re-rollable
    r2 = c.post("/api/mealie/random", json={"date": d(1), "replace_id": eid})
    assert r2.status_code == 200
    assert set(appmod._meals_rolled()) == {r2.json()["entry_id"]}


def test_route_reroll_of_a_hand_planned_dinner_is_a_409_and_changes_nothing(app_env):
    appmod, c, fake = app_env
    fake.plan.append(entry(9, d(1)))
    r = c.post("/api/mealie/random", json={"date": d(1), "replace_id": 9})
    assert r.status_code == 409 and "re-rolled" in r.json()["detail"]
    assert [e["id"] for e in fake.plan] == [9] and appmod._meals_rolled() == {}


def test_route_random_on_a_planned_day_and_bad_dates_are_clean_errors(app_env):
    appmod, c, fake = app_env
    fake.plan.append(entry(1, d(0)))
    assert c.post("/api/mealie/random", json={"date": d(0)}).status_code == 409
    assert c.post("/api/mealie/random", json={"date": "2020-01-01"}).status_code == 422
    assert c.post("/api/mealie/random", json={}).status_code == 422
    assert c.post("/api/mealie/random", json={"date": d(1), "replace_id": "x"}).status_code == 422


def test_route_shopping_ok_and_rejects_path_tricks(app_env):
    appmod, c, fake = app_env
    r = c.post("/api/mealie/shopping", json={"recipe_id": RID})
    assert r.status_code == 200 and r.json() == {"ok": True, "list": "Groceries"}
    assert c.post("/api/mealie/shopping", json={"recipe_id": "../../x"}).status_code == 422
    assert c.post("/api/mealie/shopping", json={}).status_code == 422


def test_route_image(app_env):
    appmod, c, fake = app_env
    r = c.get(f"/api/mealie/image/{RID}")
    assert r.status_code == 200 and r.content == b"IMG" and r.headers["content-type"] == "image/webp"
    assert c.get("/api/mealie/image/not-a-uuid").status_code == 404


def test_route_upstream_down_is_a_502_with_a_reason_the_wall_can_show(app_env):
    appmod, c, fake = app_env
    fake.fail[("GET", "/api/households/mealplans")] = 500
    r = c.post("/api/mealie/random", json={"date": d(1)})
    assert r.status_code == 502 and "Mealie" in r.json()["detail"]
    assert c.get("/api/tiles/mealie").json() == {"available": False, "needs_auth": False}


def test_route_rolled_set_is_bounded_and_survives_a_corrupt_kv(app_env):
    appmod, c, fake = app_env
    appmod._meals_rolled_save({i: (RID, d(1)) for i in range(1000)})
    assert len(appmod._meals_rolled()) == appmod.MEALS_ROLLED_KEEP
    assert min(appmod._meals_rolled()) == 1000 - appmod.MEALS_ROLLED_KEEP, "the newest picks are the ones kept"
    kv = lambda v: appmod.fdb.kv_set(appmod._db(), appmod.MEALS_ROLLED_KEY, v)
    kv([1, 2, 3])                                   # an older / hand-edited shape: nothing rolled
    assert appmod._meals_rolled() == {}
    kv({"1": [RID, d(1)], "x": [RID, d(1)], "2": "junk", "3": [RID], "4": [5, d(1)], "5": [None, d(2)]})
    assert appmod._meals_rolled() == {1: (RID, d(1)), 4: (None, d(1)), 5: (None, d(2))}


def test_integration_row_says_needs_auth_without_a_token(app_env, monkeypatch):
    appmod, c, fake = app_env
    assert appmod._integ_status("mealie", {}, {}) == "ok"
    monkeypatch.delenv("MEALIE_API_TOKEN")
    assert appmod._integ_status("mealie", {}, {}) == "needs_auth"


def test_health_full_reports_the_meals_source_and_the_token_setting(app_env, monkeypatch):
    appmod, c, fake = app_env
    body = c.get("/health/full").json()
    assert body["sources"]["meals"]["configured"] is True
    assert body["settings"]["mealie_token"]["ok"] is True
    monkeypatch.delenv("MEALIE_API_TOKEN")
    body = c.get("/health/full").json()
    assert body["settings"]["mealie_token"]["ok"] is False, "a missing token must fail the deploy gate"
    assert "MEALIE_API_TOKEN" in body["settings"]["mealie_token"]["why"]


def test_health_full_meals_off_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "hub.db"))
    monkeypatch.setenv("TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("DISABLE_SYNC", "1")
    monkeypatch.setenv("CONFIG_PATH", _write_cfg(tmp_path, mealie=False))
    import family_hub.app as appmod
    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        body = c.get("/health/full").json()
        assert body["sources"]["meals"]["configured"] is False
        assert body["settings"]["mealie_token"]["ok"] is True, "nothing required when meals is off"


# ======================================================== review round (2026-10-01)

def test_tile_cache_is_invalidated_by_a_write_so_the_next_read_shows_it():
    fake = FakeMealie([])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            a = await meals.meals_tile(c, mcfg(), ENV, TODAY)
            await meals.random_dinner(c, mcfg(), ENV, d(1), TODAY, {})
            b = await meals.meals_tile(c, mcfg(), ENV, TODAY)
            return a, b
    a, b = asyncio.run(go())
    assert a["days"][1]["dinner"] is None and b["days"][1]["dinner"] is not None
    assert sum(1 for m, p in fake.log if m == "GET" and p == "/api/households/mealplans") == 3, \
        "plan read, the write's own day check, then a FRESH read (not the cache)"


def test_tile_cache_expires_and_is_keyed_by_today(monkeypatch):
    fake = FakeMealie([entry(1, d(0))])
    clock = [1000.0]
    monkeypatch.setattr(meals.time, "monotonic", lambda: clock[0])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.meals_tile(c, mcfg(), ENV, TODAY)
            await meals.meals_tile(c, mcfg(), ENV, TODAY)                       # cached
            n1 = len(fake.log)
            await meals.meals_tile(c, mcfg(), ENV, TODAY + dt.timedelta(days=1))  # midnight rolled: new key
            n2 = len(fake.log)
            clock[0] += meals.MEALS_TTL + 1
            await meals.meals_tile(c, mcfg(), ENV, TODAY)                       # expired
            return n1, n2, len(fake.log)
    n1, n2, n3 = asyncio.run(go())
    assert (n1, n2, n3) == (1, 2, 3)


def test_a_read_that_started_before_a_write_does_not_cache_the_old_plan():
    """A poll from another screen is mid-read when a pick lands: its (pre-write)
    answer must not be cached over the write's invalidation."""
    fake = FakeMealie([])
    gate = asyncio.Event()
    first = {"seen": False}
    async def handler(req):
        if req.method == "GET" and req.url.path == "/api/households/mealplans" and not first["seen"]:
            first["seen"] = True
            body = {"items": []}                 # the pre-write plan
            await gate.wait()
            return httpx.Response(200, json=body)
        return fake.handler(req)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            slow = asyncio.create_task(meals.meals_tile(c, mcfg(), ENV, TODAY))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await meals.random_dinner(c, mcfg(), ENV, d(1), TODAY, {})   # write lands while the read waits
            gate.set()
            await slow
            return await meals.meals_tile(c, mcfg(), ENV, TODAY)          # must NOT be the cached old plan
    t = asyncio.run(go())
    assert t["days"][1]["dinner"] is not None, "the next read re-fetched and shows the pick"


@pytest.mark.parametrize("replace_id", [True, 1.0])
def test_reroll_rejects_bool_and_float_ids_even_when_they_equal_a_rolled_id(replace_id):
    fake = FakeMealie([entry(1, d(1))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(1, 1), replace_id=replace_id))
    assert r["ok"] is False and r["status"] == 409
    assert [e["id"] for e in fake.plan] == [1] and not any(m == "DELETE" for m, _ in fake.log)


def test_reroll_with_a_rolled_id_planned_on_another_day_is_409_and_untouched():
    fake = FakeMealie([entry(7, d(2))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is False and r["status"] == 409
    assert [e["id"] for e in fake.plan] == [7]
    assert not any(m == "DELETE" or p.endswith("/random") for m, p in fake.log)


@pytest.mark.parametrize("why,rolled,plan_entry", [
    ("the recipe was changed in Mealie", roll(7, 1, RID), entry(7, d(1), rid=RID2)),
    ("Mealie reused the id for a different date's pick", roll(7, 3, RID), entry(7, d(1), rid=RID)),
])
def test_reroll_refuses_an_entry_that_is_no_longer_what_the_hub_picked(why, rolled, plan_entry):
    fake = FakeMealie([plan_entry])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, rolled, replace_id=7))
    assert r["ok"] is False and r["status"] == 409, why
    assert [e["id"] for e in fake.plan] == [7], "a hand-chosen dinner is never replaced"


def test_tile_rolled_flag_needs_id_recipe_and_date_to_match():
    fake = FakeMealie([entry(7, d(1), rid=RID)])
    flag = lambda rolled: run(FakeMealie(list(fake.plan)), lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY, rolled)
                              )["days"][1]["dinner"]["rolled"]
    assert flag(roll(7, 1, RID)) is True
    assert flag(roll(7, 1, RID2)) is False, "different recipe"
    assert flag(roll(7, 2, RID)) is False, "different date"
    assert flag(roll(8, 1, RID)) is False, "different id"


def test_reroll_same_recipe_whose_undo_delete_fails_keeps_exactly_one_dinner():
    fake = FakeMealie([entry(7, d(1), rid=RID)])
    orig = fake.handler
    def handler(req):
        if req.method == "POST" and req.url.path.endswith("/random"):
            fake.next_id += 1
            new = entry(fake.next_id, json.loads(req.content)["date"], rid=RID)    # same recipe
            fake.plan.append(new)
            fake.log.append((req.method, req.url.path))
            return httpx.Response(200, json=new)
        if req.method == "DELETE" and req.url.path.endswith(f"/{fake.next_id}"):   # undoing the new pick fails
            fake.log.append((req.method, req.url.path))
            return httpx.Response(500, json={})
        return orig(req)
    fake.handler = handler
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is True and r["same"] is True
    assert [e["id"] for e in fake.plan] == [fake.next_id], "the old dinner is gone, one (same-recipe) dinner remains"


def test_reroll_whose_old_dinner_is_already_gone_keeps_the_new_pick():
    fake = FakeMealie([entry(7, d(1))])
    orig = fake.handler
    def handler(req):
        if req.method == "DELETE" and req.url.path.endswith("/7"):
            fake.plan = [e for e in fake.plan if e["id"] != 7]       # deleted behind our back
            fake.log.append((req.method, req.url.path))
            return httpx.Response(404, json={})
        return orig(req)
    fake.handler = handler
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is True, "a 404 on the old dinner is the outcome we wanted, not a failure"
    assert len(fake.plan) == 1 and fake.plan[0]["id"] == r["entry_id"], "the day is not left empty"


def test_reroll_that_cannot_undo_its_own_pick_says_two_dinners_are_planned():
    fake = FakeMealie([entry(7, d(1))])
    fake.fail[("DELETE", "/api/households/mealplans/")] = 500        # neither delete works
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, roll(7, 1), replace_id=7))
    assert r["ok"] is False and r["status"] == 502
    assert "two dinners" in r["error"] and "remove one in Mealie" in r["error"]
    assert len(fake.plan) == 2, "the failure is real, and it is SAID"


def test_random_requests_carry_the_right_bodies_and_query():
    fake = FakeMealie([])
    run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(2), TODAY, {}))
    get = next(c for c in fake.calls if c["method"] == "GET")
    assert get["params"] == {"start_date": d(2), "end_date": d(2), "perPage": "100"}
    post = next(c for c in fake.calls if c["method"] == "POST")
    assert post["body"] == {"date": d(2), "entryType": "dinner"}
    run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID))
    shop = [c for c in fake.calls if "/recipe/" in c["path"]][0]
    assert shop["body"] == {"recipeIncrementQuantity": 1}


def test_random_accepts_the_last_planned_day_and_rejects_the_day_after_for_any_days_setting():
    for days in (3, 5, 7):
        cfg = mcfg(days=days)
        ok = run(FakeMealie(), lambda c, cf: meals.random_dinner(c, cf, ENV, d(days - 1), TODAY, {}), cfg)
        no = run(FakeMealie(), lambda c, cf: meals.random_dinner(c, cf, ENV, d(days), TODAY, {}), cfg)
        assert ok["ok"] is True and no["status"] == 422, days


@pytest.mark.parametrize("rid", [RID + "\n", "-" * 36, " " + RID[1:], RID[:-1] + "g", RID.replace("-", "") + "xxxx"])
def test_ids_that_only_look_like_uuids_are_rejected_before_any_request(rid):
    assert meals.valid_uuid(rid) is False
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, rid))
    assert r["ok"] is False and r["status"] == 422 and fake.log == []
    assert run(fake, lambda c, cf: meals.fetch_image(c, cf, ENV, rid)) is None and fake.log == []


def test_valid_uuid_accepts_either_case_and_parse_date_rejects_a_trailing_newline():
    assert meals.valid_uuid(RID) and meals.valid_uuid(RID.upper())
    assert meals.parse_date("2026-10-01") == dt.date(2026, 10, 1)
    assert meals.parse_date("2026-10-01\n") is None


def test_non_json_replies_are_unavailable_or_a_502_never_a_409_or_a_raise():
    def html(req):
        return httpx.Response(200, content=b"<html>proxy login</html>", headers={"content-type": "text/html"})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(html)) as c:
            return (await meals.meals_tile(c, mcfg(), ENV, TODAY),
                    await meals.add_to_shopping(c, mcfg(), ENV, RID),
                    await meals.random_dinner(c, mcfg(), ENV, d(1), TODAY, {}))
    tile, shop, rnd = asyncio.run(go())
    assert tile["available"] is False
    assert shop["ok"] is False and shop["status"] == 502, "junk from Mealie is upstream trouble, not 'no shopping list'"
    assert "Expecting" not in shop["error"], "no decoder text leaks into the toast"
    assert rnd["ok"] is False and rnd["status"] == 502


def test_a_wrong_shaped_shopping_lists_reply_is_a_clear_409():
    fake = FakeMealie()
    fake.lists = "nope"
    r = run(fake, lambda c, cf: meals.add_to_shopping(c, cf, ENV, RID))
    assert r["ok"] is False and r["status"] == 409


def test_a_403_from_the_token_says_what_the_token_needs():
    fake = FakeMealie([])
    fake.fail[("POST", "/api/households/mealplans/random")] = 403
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {}))
    assert r["status"] == 502 and r["needs_auth"] is True and "edit meal plans" in r["error"]


def test_image_proxy_errors_types_size_and_cache_behaviour():
    fake = FakeMealie()
    assert run(fake, lambda c, cf: meals.fetch_image(c, cf, ENV, RID2)) == (b"IMG", "image/webp")
    # no token configured on the request: it is still tried, with NO Authorization header
    run(fake, lambda c, cf: meals.fetch_image(c, cf, {}, RID))
    # (the fake 401s without a bearer; media endpoints are public in real Mealie, the fake is stricter)
    for status in (404, 500):
        f = FakeMealie(); f.fail[("GET", "/api/media/")] = status
        assert run(f, lambda c, cf: meals.fetch_image(c, cf, ENV, RID)) is None
    def svg(req):
        return httpx.Response(200, content=b"<svg onload=alert(1)/>", headers={"content-type": "image/svg+xml"})
    def big(req):
        return httpx.Response(200, content=b"x" * (meals.IMAGE_MAX_BYTES + 1), headers={"content-type": "image/webp"})
    def with_charset(req):
        return httpx.Response(200, content=b"IMG", headers={"content-type": "image/webp; charset=binary"})
    async def one(h):
        async with httpx.AsyncClient(transport=httpx.MockTransport(h)) as c:
            return await meals.fetch_image(c, mcfg(), ENV, RID)
    meals.reset_caches()
    assert asyncio.run(one(svg)) is None, "svg can carry script: never relayed"
    assert asyncio.run(one(big)) is None, "an oversized body is not cached or relayed"
    assert asyncio.run(one(with_charset)) == (b"IMG", "image/webp"), "a content-type parameter is tolerated"


def test_image_cache_holds_exactly_the_cap_and_evicts_the_oldest():
    fake = FakeMealie()
    ids = [f"{n:036d}"[:8] + "-0000-4000-8000-" + f"{n:012d}" for n in range(meals.IMAGE_CACHE_MAX + 3)]
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            for i in ids:
                await meals.fetch_image(c, mcfg(), ENV, i)
    asyncio.run(go())
    assert list(meals._image_cache) == ids[3:], "exactly the cap, oldest first out"


def test_image_cache_entries_expire(monkeypatch):
    fake = FakeMealie()
    clock = [500.0]
    monkeypatch.setattr(meals.time, "monotonic", lambda: clock[0])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.fetch_image(c, mcfg(), ENV, RID)
            clock[0] += meals.IMAGE_TTL + 1
            await meals.fetch_image(c, mcfg(), ENV, RID)
    asyncio.run(go())
    assert sum(1 for m, p in fake.log if p.startswith("/api/media/")) == 2


# ------------------------------------------------------------ config cleaning

def test_clean_mealie_accepts_an_uppercase_scheme_and_warns_about_typos(caplog):
    assert _clean_mealie({"base": "HTTP://M:9000/"})["base"] == "HTTP://M:9000"
    with caplog.at_level(logging.WARNING, logger="family_hub.config"):
        out = _clean_mealie({"base": "http://m", "shoppinglist": "Groceries", "open-url": "http://x", "dayz": 4})
    assert out == {"base": "http://m", "days": 5}
    assert "shoppinglist" in caplog.text and "open-url" in caplog.text and "dayz" in caplog.text


@pytest.mark.parametrize("val", [5, ["Groceries"], {"a": 1}, True])
def test_clean_mealie_warns_about_a_non_text_shopping_list(val, caplog):
    with caplog.at_level(logging.WARNING, logger="family_hub.config"):
        out = _clean_mealie({"base": "http://m", "shopping_list": val})
    assert "shopping_list" not in out and "shopping_list" in caplog.text


@pytest.mark.parametrize("val", [5, ["x"], True])
def test_clean_mealie_ignores_and_warns_about_a_non_text_open_url(val, caplog):
    with caplog.at_level(logging.WARNING, logger="family_hub.config"):
        out = _clean_mealie({"base": "http://m", "open_url": val})
    assert "open_url" not in out and "open_url" in caplog.text


def test_clean_mealie_logs_when_it_clamps_days(caplog):
    with caplog.at_level(logging.WARNING, logger="family_hub.config"):
        assert _clean_mealie({"base": "http://m", "days": 0})["days"] == 3
        assert _clean_mealie({"base": "http://m", "days": 99})["days"] == 7
    assert caplog.text.count("outside") == 2


def test_load_config_round_trips_the_block(tmp_path):
    from family_hub.config import load_config
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"mealie": {"base": "http://m:9000/", "days": 4, "shopping_list": "G"}}))
    assert load_config(str(p)).mealie == {"base": "http://m:9000", "days": 4, "shopping_list": "G"}
    p.write_text(json.dumps({"mealie": "http://nope"}))
    assert load_config(str(p)).mealie is None


# --------------------------------------------------------------------- routes

def test_route_failed_reroll_leaves_the_rolled_memory_unchanged(app_env):
    appmod, c, fake = app_env
    first = c.post("/api/mealie/random", json={"date": d(1)}).json()
    before = appmod._meals_rolled()
    fake.fail[("DELETE", "/api/households/mealplans/")] = 500
    r = c.post("/api/mealie/random", json={"date": d(1), "replace_id": first["entry_id"]})
    assert r.status_code == 502
    assert appmod._meals_rolled() == before


def test_route_a_failed_memory_save_does_not_turn_a_good_pick_into_an_error(app_env, monkeypatch):
    appmod, c, fake = app_env
    def boom(_):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(appmod, "_meals_rolled_save", boom)
    r = c.post("/api/mealie/random", json={"date": d(1)})
    assert r.status_code == 200 and r.json()["ok"] is True, "Mealie already changed; the toast must say so"
    assert len(fake.plan) == 1


def test_route_two_concurrent_picks_on_one_empty_day_plan_only_one(app_env):
    appmod, c, fake = app_env
    async def go():
        return await asyncio.gather(
            appmod.mealie_random(appmod.MealsRandomIn(date=d(1))),
            appmod.mealie_random(appmod.MealsRandomIn(date=d(1))),
            return_exceptions=True)
    results = asyncio.run(go())
    oks = [r for r in results if isinstance(r, dict)]
    errs = [r for r in results if not isinstance(r, dict)]
    assert len(oks) == 1 and len(errs) == 1 and errs[0].status_code == 409
    assert len(fake.plan) == 1, "never two dinners on one day"


def test_route_concurrent_picks_on_different_days_both_stay_re_rollable(app_env):
    appmod, c, fake = app_env
    async def go():
        return await asyncio.gather(
            appmod.mealie_random(appmod.MealsRandomIn(date=d(1))),
            appmod.mealie_random(appmod.MealsRandomIn(date=d(2))))
    a, b = asyncio.run(go())
    assert set(appmod._meals_rolled()) == {a["entry_id"], b["entry_id"]}, "neither pick's memory was lost"


def test_integration_row_goes_needs_auth_after_mealie_refuses_the_token(app_env):
    appmod, c, fake = app_env
    assert appmod._integ_status("mealie", {}, {}) == "ok"
    fake.fail[("GET", "/api/households/mealplans")] = 401
    assert c.get("/api/tiles/mealie").json() == {"available": False, "needs_auth": True}
    assert appmod._integ_status("mealie", {}, {}) == "needs_auth", "a rejected token is not 'ok'"
    fake.fail.clear()
    ftiles.reset_caches()
    c.get("/api/tiles/mealie")
    assert appmod._integ_status("mealie", {}, {}) == "ok", "and it recovers when Mealie accepts it again"


def test_health_full_meals_fails_when_mealie_is_down_or_the_token_is_missing(app_env, monkeypatch):
    appmod, c, fake = app_env
    ftiles.reset_caches()
    ok = c.get("/health/full").json()
    assert ok["sources"]["meals"]["status"] == "ok" and ok["sources"]["meals"]["ok"] is True
    fake.fail[("GET", "/api/households/mealplans")] = 500
    ftiles.reset_caches()
    down = c.get("/health/full").json()
    assert down["sources"]["meals"]["ok"] is False and down["sources"]["meals"]["status"] != "ok"
    assert down["status"] == "degraded", "a broken meals source fails the deploy gate"
    fake.fail.clear()
    ftiles.reset_caches()
    monkeypatch.delenv("MEALIE_API_TOKEN")
    gone = c.get("/health/full").json()
    assert gone["settings"]["mealie_token"]["ok"] is False and gone["status"] == "degraded"


def test_health_full_names_a_meals_tile_that_crashes(app_env, monkeypatch):
    appmod, c, fake = app_env
    async def boom(*a, **k):
        raise RuntimeError("tile bug")
    monkeypatch.setattr(appmod.meals, "meals_tile", boom)
    body = c.get("/health/full").json()
    assert body["sources"]["meals"]["ok"] is False
    assert "health check crashed" in (body["sources"]["meals"].get("last_error") or "")


def test_startup_says_so_when_meals_is_configured_without_a_token(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "hub.db"))
    monkeypatch.setenv("TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("DISABLE_SYNC", "1")
    monkeypatch.delenv("MEALIE_API_TOKEN", raising=False)
    monkeypatch.setenv("CONFIG_PATH", _write_cfg(tmp_path))
    import family_hub.app as appmod
    importlib.reload(appmod)
    with caplog.at_level(logging.ERROR):
        with TestClient(appmod.app):
            pass
    assert "MEALIE_API_TOKEN is empty" in caplog.text


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


@pytest.mark.parametrize("body", [[], "x", 5, {"listItems": "x"}, {}])
def test_shopping_read_with_no_item_list_is_unavailable_never_a_reassuring_empty_list(body):
    """A changed reply shape (a Mealie upgrade, a paginated endpoint) must read as
    unavailable, not as 'Nothing on the list': an empty card that is not empty is worse."""
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
    assert out == {"available": False, "needs_auth": False}
    assert meals._shop_cache == {}


@pytest.mark.parametrize("body", [{"listItems": [None, 5]}, {"listItems": []}])
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


# ------------------------------------------------------------ shopping routes

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
    assert c.delete("/api/mealie/shopping/items/..%2F..%2Fx").status_code in (404, 405, 422)
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


# ------------------------------------------------- review fixes (final review)

def test_shopping_read_cap_keeps_every_open_item_even_when_checked_ones_come_first_in_mealies_order():
    """The cap must apply AFTER the unchecked-first sort: 50 checked items listed first in
    Mealie's own order must not push open items out of the capped read."""
    checked = [item(f"{n:08d}-0000-4000-8000-000000000000", f"Done {n}", checked=True, position=n)
               for n in range(50)]
    openn = [item(f"{n:08d}-1111-4111-8111-111111111111", f"Open {n}", position=100 + n)
             for n in range(meals.SHOPPING_MAX_ITEMS)]
    out = shop(FakeMealie(items=checked + openn))
    assert len(out["items"]) == meals.SHOPPING_MAX_ITEMS
    assert all(not i["checked"] for i in out["items"]), "no open item was cut for a checked one"
    assert out["open"] == meals.SHOPPING_MAX_ITEMS


def test_shopping_read_names_a_misconfigured_list_instead_of_a_generic_outage():
    out = shop(FakeMealie(lists=[]))
    assert out["available"] is False and out["needs_auth"] is False
    assert "no shopping list" in out["reason"]
    out = shop(FakeMealie(), cfg=mcfg(shopping_list="Grocery"))
    assert out["available"] is False and "Grocery" in out["reason"]


def test_check_keeps_every_field_of_a_recipe_derived_item_that_mealie_returned():
    """Mealie's update replaces the item, so everything except the read-only fields rides
    back unchanged: a recipe-derived item must keep its recipe link, food and unit."""
    refs = [{"recipeId": RID, "recipeQuantity": 1.0, "recipeScale": 1.0, "id": "r1", "shoppingListItemId": IID1}]
    fake = FakeMealie(items=[item(IID1, "2 cups flour", foodId="f1", unitId="u1", labelId=None,
                                  recipeReferences=refs, food={"id": "f1", "name": "flour"},
                                  unit={"id": "u1", "name": "cup"}, createdAt="x", updatedAt="y",
                                  groupId="g", householdId="h", userId="u")])
    assert check(fake, IID1, True) == {"ok": True}
    body = next(c for c in fake.calls if c["method"] == "PUT")["body"]
    assert body["recipeReferences"] == refs and body["food"] == {"id": "f1", "name": "flour"}
    assert body["unit"] == {"id": "u1", "name": "cup"} and body["foodId"] == "f1" and body["unitId"] == "u1"
    assert body["checked"] is True and body["shoppingListId"] == RID2
    for read_only in ("id", "createdAt", "updatedAt", "display", "groupId", "householdId", "userId"):
        assert read_only not in body, read_only


def test_adding_a_recipes_ingredients_drops_the_cached_shopping_list():
    """The Meals card's add-to-list changes the same list the Shopping card shows."""
    fake = FakeMealie(items=[item(IID1, "Milk")])
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            await meals.shopping_tile(c, mcfg(), ENV)
            assert meals._shop_cache, "the read was cached"
            await meals.add_to_shopping(c, mcfg(), ENV, RID)
            return dict(meals._shop_cache)
    assert asyncio.run(go()) == {}


def test_concurrent_shopping_writes_are_serialized_by_the_route_lock(app_env):
    """Two phones tapping the same item at once: the second write must not start reading
    the item until the first has finished writing it."""
    appmod, c, fake = app_env
    fake.items.append(item(IID1, "Milk"))
    inner = fake.handler
    async def go():
        gate = asyncio.Event()
        first = {"held": False}
        async def handler(req):
            if (req.method == "GET" and req.url.path == f"/api/households/shopping/items/{IID1}"
                    and not first["held"]):
                first["held"] = True
                await gate.wait()                    # the first write stalls mid-read
            return inner(req)
        appmod._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        t1 = asyncio.create_task(appmod.mealie_shopping_check(IID1, appmod.ShoppingCheckIn(checked=True)))
        for _ in range(5):
            await asyncio.sleep(0)
        t2 = asyncio.create_task(appmod.mealie_shopping_check(IID1, appmod.ShoppingCheckIn(checked=False)))
        for _ in range(20):
            await asyncio.sleep(0)
        item_gets_while_first_is_stalled = sum(
            1 for m, p in fake.log if m == "GET" and p == f"/api/households/shopping/items/{IID1}")
        gate.set()
        await asyncio.gather(t1, t2)
        await appmod._http.aclose()
        return item_gets_while_first_is_stalled
    stalled = asyncio.run(go())
    # the stalled first read is not logged until it is released, so with the lock nothing
    # has reached Mealie's item endpoint yet; an unlocked second write would already have
    assert stalled == 0, "the second write read the item while the first was still in flight (no lock)"
    order = [(m, p.rsplit("/", 1)[-1]) for m, p in fake.log if "/shopping/items/" in p]
    assert order == [("GET", IID1), ("PUT", IID1), ("GET", IID1), ("PUT", IID1)]


def test_a_free_text_item_shows_its_note_not_mealies_quantity_prefixed_display():
    """Verified against a real Mealie 3.28: a quick-added item (no food) comes back with
    display '1 Milk' (the quantity 1 is prefixed) and note 'Milk'. The card must show the
    note, or every item added from the wall reads '1 Milk'."""
    fake = FakeMealie(items=[item(IID1, "1 Milk", note="Milk", foodId=None)])
    assert shop(fake)["items"][0]["text"] == "Milk"


def test_a_recipe_derived_item_still_shows_mealies_display_with_its_quantity_and_unit():
    fake = FakeMealie(items=[item(IID1, "2 cups flour", note="", foodId="f1",
                                  food={"id": "f1", "name": "flour"})])
    assert shop(fake)["items"][0]["text"] == "2 cups flour"
    fake = FakeMealie(items=[item(IID1, "2 cups flour", note="sifted", foodId="f1")])
    assert shop(fake)["items"][0]["text"] == "2 cups flour", "a food item uses display even when it has a note"


def test_a_food_less_item_with_no_note_falls_back_to_display():
    fake = FakeMealie(items=[item(IID1, "1 something", note="  ", foodId=None)])
    assert shop(fake)["items"][0]["text"] == "1 something"



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


@pytest.mark.parametrize("servings,want", [(6, 6), (6.0, 6), (2.5, 2.5), (0, None), (-1, None),
                                           ("6", None), (True, None), (None, None)])
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
    fake = FakeMealie(details={f"r-{n}": detail_body(slug=f"r-{n}")
                               for n in range(meals.RECIPE_DETAIL_CACHE_MAX + 5)})
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
                # a real UUID shape: f"{n:036d}" is not one and would cache nothing
                await meals.fetch_image(c, mcfg(), ENV, f"{n:08d}-0000-4000-8000-000000000000", "tiny")
    asyncio.run(go())
    assert meals.IMAGE_CACHE_MAX < len(meals._thumb_cache) <= meals.THUMB_CACHE_MAX



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
