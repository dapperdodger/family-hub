"""The Meals card's backend: config cleaning, the registry entry, the fail-soft
Mealie read, the three writes (random dinner / re-roll, add to shopping list),
the photo proxy, and the routes (including the persisted re-roll safety)."""
import asyncio
import datetime as dt
import importlib
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from family_hub import integrations, meals, tiles
from family_hub.config import Config, _clean_mealie

TODAY = dt.date(2026, 10, 1)
RID = "08481e68-b32a-45db-9f99-f036126dba27"
RID2 = "9cc3dd7f-6004-48f8-b70a-188022e816b9"
ENV = {"MEALIE_API_TOKEN": "tok"}


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


class FakeMealie:
    """A tiny Mealie: a plan, shopping lists, and a log of every request."""

    def __init__(self, plan=None, lists=None):
        self.plan = list(plan or [])
        self.lists = lists if lists is not None else [{"id": RID2, "name": "Groceries"}]
        self.log = []
        self.fail = {}          # (METHOD, path-prefix) -> status
        self.next_id = 100

    def handler(self, req):
        self.log.append((req.method, req.url.path))
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
            self.plan = [e for e in self.plan if e["id"] != eid]
            return httpx.Response(200, json={})
        if req.method == "GET" and p == "/api/households/shopping/lists":
            return httpx.Response(200, json={"items": self.lists})
        if req.method == "POST" and "/shopping/lists/" in p and p.endswith(f"/recipe/{RID}"):
            return httpx.Response(200, json={})
        if req.method == "GET" and p.startswith("/api/media/recipes/"):
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


def test_tile_ignores_other_meal_types_and_empty_notes():
    fake = FakeMealie([entry(1, d(0), entryType="lunch"),
                       {"id": 2, "date": d(0), "entryType": "dinner", "title": "", "recipe": None},
                       {"id": 3, "date": d(1), "entryType": "dinner", "title": "Leftovers", "recipe": None}])
    t = run(fake, lambda c, cf: meals.meals_tile(c, cf, ENV, TODAY))
    assert t["days"][0]["dinner"] is None
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
    assert t["days"][0]["dinner"] is None
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
            a = await meals.meals_tile(c, mcfg(), ENV, TODAY, set())
            b = await meals.meals_tile(c, mcfg(), ENV, TODAY, {1})
            return a, b
    a, b = asyncio.run(go())
    assert len(fake.log) == 1, "second read came from the cache"
    assert a["days"][0]["dinner"]["rolled"] is False
    assert b["days"][0]["dinner"]["rolled"] is True, "rolled is recomputed, not cached"


# ------------------------------------------------------------ random + re-roll

def test_random_plans_an_empty_day():
    fake = FakeMealie([entry(1, d(0))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(2), TODAY, set()))
    assert r["ok"] is True and isinstance(r["entry_id"], int)
    assert any(e["date"] == d(2) for e in fake.plan)


def test_random_refuses_a_day_that_already_has_a_dinner():
    fake = FakeMealie([entry(1, d(0))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(0), TODAY, set()))
    assert r["ok"] is False and r["status"] == 409
    assert ("POST", "/api/households/mealplans/random") not in fake.log


@pytest.mark.parametrize("date", [d(-1), d(5), d(40), "2026-13-01", "nope", "", None, 5, "2026-10-1"])
def test_random_rejects_dates_outside_the_planned_days(date):
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, date, TODAY, set()))
    assert r["ok"] is False and r["status"] == 422 and fake.log == []


def test_reroll_replaces_only_a_dinner_this_hub_picked_new_first_then_delete():
    fake = FakeMealie([entry(7, d(1))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
    assert r["ok"] is True
    assert [e["id"] for e in fake.plan] == [r["entry_id"]]
    posts = [i for i, (m, p) in enumerate(fake.log) if p.endswith("/random")]
    dels = [i for i, (m, p) in enumerate(fake.log) if m == "DELETE"]
    assert posts and dels and posts[0] < dels[0], "the new pick is made BEFORE the old one goes"


@pytest.mark.parametrize("replace_id", [7, "7", True, 1.0, -1])
def test_reroll_of_a_dinner_not_in_the_rolled_set_is_refused(replace_id):
    fake = FakeMealie([entry(7, d(1))])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, set(), replace_id=replace_id))
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
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
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
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
    assert r["ok"] is True and len(fake.plan) == 1, "never loops forever, never leaves two dinners"
    assert sum(1 for m, p in fake.log if p.endswith("/random")) == meals.RANDOM_TRIES


def test_reroll_of_a_dinner_that_vanished_is_a_409_not_a_blind_delete():
    fake = FakeMealie([])
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
    assert r["ok"] is False and r["status"] == 409
    assert fake.log and not any(m in ("DELETE",) or p.endswith("/random") for m, p in fake.log)


def test_reroll_that_cannot_remove_the_old_dinner_undoes_the_new_pick():
    fake = FakeMealie([entry(7, d(1))])
    fake.fail[("DELETE", "/api/households/mealplans/7")] = 500
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
    assert r["ok"] is False and r["status"] == 502
    assert [e["id"] for e in fake.plan] == [7], "the day still shows exactly the old dinner"


def test_random_upstream_failure_is_a_502_with_a_reason_and_no_delete():
    fake = FakeMealie([entry(7, d(1))])
    fake.fail[("POST", "/api/households/mealplans/random")] = 500
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, ENV, d(1), TODAY, {7}, replace_id=7))
    assert r["ok"] is False and r["status"] == 502 and "Mealie" in r["error"]
    assert [e["id"] for e in fake.plan] == [7]


def test_random_with_a_malformed_reply_fails_cleanly():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json={"no": "id"})
        return httpx.Response(200, json={"items": []})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meals.random_dinner(c, mcfg(), ENV, d(1), TODAY, set())
    r = asyncio.run(go())
    assert r["ok"] is False and r["status"] == 502


def test_writes_without_a_token_or_config_are_refused_without_a_request():
    fake = FakeMealie()
    r = run(fake, lambda c, cf: meals.random_dinner(c, cf, {}, d(1), TODAY, set()))
    assert r["ok"] is False and r["status"] == 503 and r["needs_auth"] is True
    r = run(fake, lambda c, cf: meals.random_dinner(c, Config(), ENV, d(1), TODAY, set()))
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
    assert eid in appmod._meals_rolled()
    t = c.get("/api/tiles/mealie").json()
    assert t["days"][1]["dinner"]["rolled"] is True, "the card is told it may re-roll this one"
    # re-roll swaps the remembered id, so only the NEW pick stays re-rollable
    r2 = c.post("/api/mealie/random", json={"date": d(1), "replace_id": eid})
    assert r2.status_code == 200
    assert appmod._meals_rolled() == {r2.json()["entry_id"]}


def test_route_reroll_of_a_hand_planned_dinner_is_a_409_and_changes_nothing(app_env):
    appmod, c, fake = app_env
    fake.plan.append(entry(9, d(1)))
    r = c.post("/api/mealie/random", json={"date": d(1), "replace_id": 9})
    assert r.status_code == 409 and "re-rolled" in r.json()["detail"]
    assert [e["id"] for e in fake.plan] == [9] and appmod._meals_rolled() == set()


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
    appmod._meals_rolled_save(set(range(1000)))
    assert len(appmod._meals_rolled()) == appmod.MEALS_ROLLED_KEEP
    appmod.fdb.kv_set(appmod._db(), appmod.MEALS_ROLLED_KEY, {"not": "a list"})
    assert appmod._meals_rolled() == set()
    appmod.fdb.kv_set(appmod._db(), appmod.MEALS_ROLLED_KEY, [1, "x", True, None, 2])
    assert appmod._meals_rolled() == {1, 2}


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
