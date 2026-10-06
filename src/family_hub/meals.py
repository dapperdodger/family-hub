"""Meals card: tonight's dinner and the next few days, from a Mealie server.

Like the other tile proxies, every read fails soft: a dead or misbehaving
Mealie yields ``{"available": False}``, never an exception (the routes have no
global handler, so a raise would be a 500 on the wall). The API token is a
secret and comes ONLY from the environment (MEALIE_API_TOKEN); the config block
carries just the non-secret bits (see config._clean_mealie).

Three writes ride on top of the read, all behind validated inputs because they
put caller text into upstream URL paths:

* ``random_dinner`` plans a random recipe on an EMPTY day, or (re-roll)
  replaces a dinner this hub itself picked. A hand-planned dinner is never
  replaced: only an entry the hub picked (``rolled``: entry id -> (the recipe it
  picked, the date it picked it for)) may be re-rolled, and only while it still
  holds that recipe on that date (an entry edited in Mealie, or an id Mealie
  reused for something else, no longer qualifies).
* ``add_to_shopping`` adds a recipe's ingredients to a shopping list.
* ``fetch_image`` proxies a recipe photo, so the browser needs no route to
  Mealie and never sees the token.

Writes return ``{"ok": bool, "error"?: str, "status"?: int}`` and never raise.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
import uuid

import httpx

from . import tiles
from .integrations import mealie_token

log = logging.getLogger("family_hub.meals")

TIMEOUT = tiles.TIMEOUT
MEALS_TTL = 20.0                # a plan changes when someone edits it, not by the second
IMAGE_TTL = 3600.0
IMAGE_CACHE_MAX = 16
IMAGE_MAX_BYTES = 3_000_000
IMAGE_TYPES = {"image/webp", "image/png", "image/jpeg", "image/gif", "image/avif"}   # never svg
DESCRIPTION_MAX = 200
MAX_PLAN_ITEMS = 100
RANDOM_TRIES = 3                # a re-roll draws again if it lands on the same recipe
RANDOM_BUDGET_S = 6.0           # stop drawing again past this (the wall's own request gives up at 12s)
SHOPPING_TTL = 10.0             # a list changes when someone edits it; the card re-reads every minute anyway
SHOPPING_MAX_ITEMS = 200
ITEM_TEXT_MAX = 120

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# (base, today, days) -> (expiry monotonic, result). Only good reads are cached.
_cache: dict[tuple, tuple[float, dict]] = {}
# Bumped by every write (even a failed one: Mealie may have changed). A read
# that STARTED before a write must not cache its pre-write answer after it.
_gen = 0
# recipe id -> (expiry monotonic, bytes, content type)
_image_cache: dict[str, tuple[float, bytes, str]] = {}
# Mealie base -> (expiry monotonic, result). Only good reads are cached.
_shop_cache: dict[str, tuple[float, dict]] = {}
# Bumped by every shopping write (even a failed one) and by the wall's refresh; a read
# that STARTED before it must not cache its pre-write answer after it (same idea as _gen).
_shop_gen = 0


def reset_caches() -> None:
    _cache.clear()
    _image_cache.clear()
    _shop_cache.clear()


def forget_plan() -> None:
    """Drop the cached meal plan and shopping list so the next read goes to Mealie
    (the wall's refresh button). Recipe photos stay cached."""
    _invalidate()
    _invalidate_shopping()


def _invalidate() -> None:
    global _gen
    _gen += 1
    _cache.clear()


def _invalidate_shopping() -> None:
    global _shop_gen
    _shop_gen += 1
    _shop_cache.clear()


def _headers(env: dict) -> dict:
    return {"Authorization": f"Bearer {mealie_token(env)}"}


def valid_uuid(value: object) -> bool:
    """True only for a canonical UUID string (8-4-4-4-12 hex, either case, no
    surrounding whitespace or newline). These ids go into upstream URL paths, so
    "looks UUID-ish" is not enough: a trailing newline or a run of dashes must
    not get through."""
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def parse_date(value: object) -> dt.date | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _auth_failed(e: BaseException) -> bool:
    return (isinstance(e, httpx.HTTPStatusError)
            and e.response.status_code in (401, 403))


def _error_text(e: BaseException) -> str:
    """A short, honest reason for the card, never the raw exception."""
    if _auth_failed(e):
        return "Mealie refused the API token (it needs to be able to edit meal plans and shopping lists)"
    if isinstance(e, (httpx.TransportError, OSError)):
        return "Mealie is unreachable"
    if isinstance(e, httpx.HTTPStatusError):
        return f"Mealie answered {e.response.status_code}"
    return "Mealie sent something unexpected"


async def _plan(client, mc: dict, env: dict, start: dt.date, end: dt.date) -> list[dict]:
    """The dinner entries between start and end (inclusive), as the raw dicts
    Mealie sent. Raises on a transport/HTTP/shape problem (callers catch)."""
    r = await client.get(
        f"{mc['base']}/api/households/mealplans",
        params={"start_date": start.isoformat(), "end_date": end.isoformat(),
                "perPage": MAX_PLAN_ITEMS},
        headers=_headers(env), timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise ValueError("mealplans reply has no items list")
    return [i for i in items if isinstance(i, dict)]


def _dinner(entry: dict) -> dict | None:
    """One plan entry as the card's dinner, or None when it is not a dinner or
    has nothing to show. Every field is type-guarded: a valid-but-wrong body
    must degrade the row, not raise."""
    if entry.get("entryType") != "dinner":
        return None
    recipe = entry.get("recipe") if isinstance(entry.get("recipe"), dict) else {}
    name = recipe.get("name") if isinstance(recipe.get("name"), str) else ""
    if not name.strip():
        t = entry.get("title")
        name = t if isinstance(t, str) else ""
    name = name.strip() or "Dinner planned"   # an unnamed entry still OCCUPIES the day
    desc = recipe.get("description") if isinstance(recipe.get("description"), str) else ""
    rid = recipe.get("id") if valid_uuid(recipe.get("id")) else (
        entry.get("recipeId") if valid_uuid(entry.get("recipeId")) else None)
    return {
        "id": entry["id"] if _is_int(entry.get("id")) else None,
        "recipe_id": rid,
        "name": name[:120],
        "description": desc.strip()[:DESCRIPTION_MAX],
        "has_image": bool(rid and recipe.get("image")),
    }


async def meals_tile(client, cfg, env: dict, today: dt.date,
                     rolled: dict[int, tuple[str | None, str]] | None = None) -> dict:
    """``{available, needs_auth?, days: [{date, dinner}], open_url}``.

    ``dinner`` is None for an empty day, else ``{id, recipe_id, name,
    description, has_image, rolled, more}``. ``rolled`` (entry id ->
    (recipe, date) the hub picked) marks the entries this hub picked itself and
    that still hold that recipe on that date: the only ones the card offers to re-roll. Never
    raises; errors are never cached."""
    rolled = rolled or {}
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"available": False}
    if not mealie_token(env):
        tiles._note_error("meals", "MEALIE_API_TOKEN is not set")
        return {"available": False, "needs_auth": True}
    key = (mc["base"], today.isoformat(), mc["days"])
    hit = _cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return _with_rolled(hit[1], rolled)
    end = today + dt.timedelta(days=mc["days"] - 1)
    gen = _gen
    try:
        items = await _plan(client, mc, env, today, end)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
        log.warning("meals tile unavailable: %s", e)
        tiles._note_error("meals", e)
        _note_auth(e)
        return {"available": False, "needs_auth": _auth_failed(e)}
    by_day: dict[str, list[dict]] = {}
    for entry in sorted(items, key=lambda x: x["id"] if _is_int(x.get("id")) else 1 << 60):
        d = entry.get("date")
        dinner = _dinner(entry)
        if isinstance(d, str) and dinner is not None:
            by_day.setdefault(d, []).append(dinner)
    days = []
    for i in range(mc["days"]):
        d = (today + dt.timedelta(days=i)).isoformat()
        got = by_day.get(d) or []
        days.append({"date": d, "dinner": ({**got[0], "more": len(got) - 1} if got else None)})
    result = {"available": True, "days": days, "open_url": mc.get("open_url") or mc["base"]}
    tiles._note_ok("meals", None, auth_rejected=None)
    if gen == _gen:                  # a write landed while we were reading: don't cache the old plan
        _cache[key] = (time.monotonic() + MEALS_TTL, result)
    return _with_rolled(result, rolled)


def _with_rolled(result: dict, rolled) -> dict:
    """The cached read with each dinner's ``rolled`` flag set from the CURRENT
    rolled map (it changes without the plan changing). The id, the recipe AND the
    date must all match: an entry edited in Mealie, or an id Mealie reused for a
    hand-planned dinner, is a dinner somebody chose, not one the hub picked."""
    days = []
    for d in result["days"]:
        dn = d["dinner"]
        days.append({"date": d["date"], "dinner": (
            {**dn, "rolled": rolled.get(dn["id"]) == (dn["recipe_id"], d["date"])} if dn else None)})
    return {**result, "days": days}


def _note_auth(e: BaseException) -> None:
    tiles.SOURCE_STATE.setdefault("meals", {})["auth_rejected"] = _auth_failed(e) or None


def _fail(e: BaseException) -> dict:
    _note_auth(e)
    return {"ok": False, "error": _error_text(e), "needs_auth": _auth_failed(e)}


async def random_dinner(client, cfg, env: dict, date_str: object, today: dt.date,
                        rolled, replace_id: object = None) -> dict:
    """Plan a random dinner on ``date_str``. Returns ``{ok, entry_id, recipe_id,
    same}`` or ``{ok: False, error, status}``.

    Empty day: plans a random recipe. With ``replace_id`` (a re-roll): that id
    must be a dinner this hub picked (``rolled``: id -> (recipe, date)), still
    be on that date, and still hold that recipe. The new pick is made
    FIRST and the old one removed after, so a failure never leaves the day
    empty; a failed removal rolls the new pick back (and says so when even that
    fails). A re-roll that keeps landing on the same recipe draws again a few
    times, then reports ``same`` instead of pretending it changed."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"ok": False, "error": "Meals is not configured", "status": 404}
    if not mealie_token(env):
        return {"ok": False, "error": "MEALIE_API_TOKEN is not set", "status": 503,
                "needs_auth": True}
    day = parse_date(date_str)
    if day is None or not (today <= day < today + dt.timedelta(days=mc["days"])):
        return {"ok": False, "error": "date is outside the planned days", "status": 422}
    if replace_id is not None and (not _is_int(replace_id) or replace_id not in rolled):
        return {"ok": False, "status": 409,
                "error": "only a dinner picked here can be re-rolled"}
    base = mc["base"]
    mealplans = f"{base}/api/households/mealplans"
    try:
        try:
            plan = await _plan(client, mc, env, day, day)
            existing = [e for e in plan if e.get("entryType") == "dinner"]
            if replace_id is None and existing:
                return {"ok": False, "status": 409, "error": "that day already has a dinner"}
            old_rid = None
            if replace_id is not None:
                old = next((e for e in existing if e.get("id") == replace_id), None)
                if old is None:
                    return {"ok": False, "status": 409, "error": "that dinner is gone from the plan"}
                od = _dinner(old)
                old_rid = od["recipe_id"] if od else None
                if rolled.get(replace_id) != (old_rid, day.isoformat()):
                    return {"ok": False, "status": 409,
                            "error": "that dinner was changed in Mealie since it was picked here"}
            deadline = time.monotonic() + RANDOM_BUDGET_S
            for attempt in range(RANDOM_TRIES):
                r = await client.post(f"{mealplans}/random",
                                      json={"date": day.isoformat(), "entryType": "dinner"},
                                      headers=_headers(env), timeout=TIMEOUT)
                r.raise_for_status()
                body = r.json()
                new_id = body.get("id") if isinstance(body, dict) else None
                if not _is_int(new_id):
                    raise ValueError("random reply has no entry id")
                new_rid = body.get("recipeId") if valid_uuid(body.get("recipeId")) else None
                same = old_rid is not None and new_rid == old_rid
                if not same or attempt == RANDOM_TRIES - 1 or time.monotonic() > deadline:
                    break
                try:   # same recipe again: undo that pick and draw once more
                    dr = await client.delete(f"{mealplans}/{new_id}", headers=_headers(env), timeout=TIMEOUT)
                    if dr.status_code != 404:
                        dr.raise_for_status()
                except httpx.HTTPError as e:
                    # can't undo it: KEEP it. It is the same recipe as the old dinner, the old
                    # one is removed below, and the day is left with exactly one dinner.
                    log.warning("meals re-roll: could not undo a same-recipe pick: %s", e)
                    break
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            log.warning("meals random failed: %s", e)
            return {**_fail(e), "status": 502}
        if replace_id is not None:
            try:
                d = await client.delete(f"{mealplans}/{replace_id}", headers=_headers(env), timeout=TIMEOUT)
                if d.status_code != 404:       # already gone is exactly what we wanted
                    d.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("meals re-roll: removing the old dinner failed: %s", e)
                undone = True
                try:   # undo the new pick so the day still shows ONE dinner, the old one
                    u = await client.delete(f"{mealplans}/{new_id}", headers=_headers(env), timeout=TIMEOUT)
                    if u.status_code != 404:
                        u.raise_for_status()
                except httpx.HTTPError:
                    undone = False
                    log.warning("meals re-roll: could not undo the new pick either")
                err = _fail(e)
                if not undone:
                    err["error"] += " -- two dinners are now planned for that day; remove one in Mealie"
                return {**err, "status": 502}
        return {"ok": True, "entry_id": new_id, "recipe_id": new_rid,
                "same": replace_id is not None and same}
    finally:
        _invalidate()           # Mealie may have changed, even on a failure: never serve the old plan


async def _shopping_list(client, mc: dict, env: dict) -> tuple[str, str]:
    """(list id, list name): the configured list (an id, or a name matched
    case-insensitively), else the first list Mealie has. Raises ValueError when
    there is none."""
    r = await client.get(f"{mc['base']}/api/households/shopping/lists",
                         params={"perPage": 50}, headers=_headers(env), timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else None
    lists = [i for i in (items or []) if isinstance(i, dict) and valid_uuid(i.get("id"))]
    want = (mc.get("shopping_list") or "").strip()
    if want:
        for i in lists:
            if i["id"] == want or str(i.get("name", "")).strip().lower() == want.lower():
                return i["id"], str(i.get("name") or "")
        raise ValueError(f"no shopping list matches {want!r}")
    if not lists:
        raise ValueError("Mealie has no shopping list yet")
    return lists[0]["id"], str(lists[0].get("name") or "")


async def add_to_shopping(client, cfg, env: dict, recipe_id: object) -> dict:
    """Add a recipe's ingredients to the shopping list. ``{ok, list?}``."""
    mc = getattr(cfg, "mealie", None)
    if not mc:
        return {"ok": False, "error": "Meals is not configured", "status": 404}
    if not mealie_token(env):
        return {"ok": False, "error": "MEALIE_API_TOKEN is not set", "status": 503,
                "needs_auth": True}
    if not valid_uuid(recipe_id):
        return {"ok": False, "error": "not a recipe id", "status": 422}
    try:
        list_id, list_name = await _shopping_list(client, mc, env)
        r = await client.post(
            f"{mc['base']}/api/households/shopping/lists/{list_id}/recipe/{recipe_id}",
            json={"recipeIncrementQuantity": 1}, headers=_headers(env), timeout=TIMEOUT)
        r.raise_for_status()
    except json.JSONDecodeError as e:     # before ValueError (it is one): Mealie sent junk, not "no list"
        log.warning("meals add-to-shopping: non-JSON reply: %s", e)
        return {**_fail(e), "status": 502}
    except ValueError as e:
        return {"ok": False, "error": str(e)[:120], "status": 409}
    except httpx.HTTPError as e:
        log.warning("meals add-to-shopping failed: %s", e)
        return {**_fail(e), "status": 502}
    finally:
        _invalidate_shopping()           # the Shopping card shows this same list: never serve it stale
    return {"ok": True, "list": list_name}


def _shopping_item(raw: dict) -> dict | None:
    """One list entry as the card shows it, or None when it cannot be shown. A
    recipe-derived item has a computed ``display`` ("2 cups flour"); a free-text one
    has just a ``note``."""
    iid = raw.get("id")
    if not valid_uuid(iid):
        return None
    display, note = raw.get("display"), raw.get("note")
    usable = lambda v: isinstance(v, str) and bool(v.strip())   # noqa: E731
    has_food = bool(raw.get("foodId")) or isinstance(raw.get("food"), dict)
    # A food item shows Mealie's display ("2 cups flour"). A free-text one (no food) shows
    # its note: Mealie prefixes the quantity to its display ("1 Milk" for a quick-add of
    # "Milk"), which is wrong for something typed by hand.
    first, second = (display, note) if has_food else (note, display)
    text = first if usable(first) else second
    if not usable(text):
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
    except json.JSONDecodeError as e:     # before ValueError (it is one): Mealie sent junk, not "no list"
        log.warning("meals shopping unavailable: %s", e)
        _note_auth(e)
        return {"available": False, "needs_auth": False}
    except ValueError as e:
        # no list yet, or `shopping_list` names none: a configuration problem, said as such
        # (a mistyped list name must not read as a dead server)
        log.warning("meals shopping unavailable: %s", e)
        return {"available": False, "needs_auth": False, "reason": str(e)[:120]}
    except httpx.HTTPError as e:
        log.warning("meals shopping unavailable: %s", e)
        _note_auth(e)
        return {"available": False, "needs_auth": _auth_failed(e)}
    raw_items = body.get("listItems") if isinstance(body, dict) else None
    if not isinstance(raw_items, list):
        # a changed reply shape (a Mealie upgrade, a paginated endpoint) is not an empty list
        log.warning("meals shopping: the list reply carries no listItems list")
        return {"available": False, "needs_auth": False}
    rows = []
    for n, raw in enumerate(raw_items):
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


# What a check/un-check sends back. Mealie's update REPLACES the item, so everything it
# returned rides back unchanged except the read-only fields: a deny-list, not an
# allow-list, so a field we did not think of is never dropped. Verified against a real
# Mealie 3.28 (2026-10-06): display, quantity, food, unit, label and note all survive a
# check. recipeReferences does NOT: Mealie clears an item's link to its recipe on ANY
# update (the single PUT with the references whole or trimmed, without them, and the bulk
# PUT all gave 1 -> 0), so it cannot be preserved from here. What is lost is only
# Mealie's own "remove this recipe's ingredients" for that item, not anything shown.
_ITEM_READONLY = ("id", "createdAt", "updatedAt", "display", "groupId", "householdId", "userId")
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
        body = {k: v for k, v in found.items() if k not in _ITEM_READONLY}
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


async def fetch_image(client, cfg, env: dict, recipe_id: object) -> tuple[bytes, str] | None:
    """A recipe photo as (bytes, content type), or None. Cached for an hour."""
    mc = getattr(cfg, "mealie", None)
    if not mc or not valid_uuid(recipe_id):
        return None
    hit = _image_cache.get(recipe_id)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1], hit[2]
    try:
        r = await client.get(
            f"{mc['base']}/api/media/recipes/{recipe_id}/images/min-original.webp",
            headers=_headers(env) if mealie_token(env) else {}, timeout=TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("meals image %s unavailable: %s", recipe_id, e)
        return None
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in IMAGE_TYPES or len(r.content) > IMAGE_MAX_BYTES:
        return None
    if len(_image_cache) >= IMAGE_CACHE_MAX:
        _image_cache.pop(next(iter(_image_cache)))
    _image_cache[recipe_id] = (time.monotonic() + IMAGE_TTL, r.content, ctype)
    return r.content, ctype
