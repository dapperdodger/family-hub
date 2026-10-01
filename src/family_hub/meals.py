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
  replaced: only ids in the ``rolled`` set may be re-rolled.
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

import httpx

from . import tiles
from .integrations import mealie_token

log = logging.getLogger("family_hub.meals")

TIMEOUT = tiles.TIMEOUT
MEALS_TTL = 20.0                # a plan changes when someone edits it, not by the second
IMAGE_TTL = 3600.0
IMAGE_CACHE_MAX = 16
DESCRIPTION_MAX = 200
MAX_PLAN_ITEMS = 100
RANDOM_TRIES = 3                # a re-roll draws again if it lands on the same recipe

_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (base, today, days) -> (expiry monotonic, result). Only good reads are cached.
_cache: dict[tuple, tuple[float, dict]] = {}
# recipe id -> (expiry monotonic, bytes, content type)
_image_cache: dict[str, tuple[float, bytes, str]] = {}


def reset_caches() -> None:
    _cache.clear()
    _image_cache.clear()


def _headers(env: dict) -> dict:
    return {"Authorization": f"Bearer {mealie_token(env)}"}


def valid_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID.match(value))


def parse_date(value: object) -> dt.date | None:
    if not isinstance(value, str) or not _DATE.match(value):
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
        return "Mealie rejected the API token"
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
    name = name.strip()
    if not name:
        return None
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
                     rolled: set[int] | frozenset[int] = frozenset()) -> dict:
    """``{available, needs_auth?, days: [{date, dinner}], open_url}``.

    ``dinner`` is None for an empty day, else ``{id, recipe_id, name,
    description, has_image, rolled, more}``. ``rolled`` marks the entries this
    hub picked itself (the only ones the card offers to re-roll). Never raises;
    errors are never cached."""
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
    try:
        items = await _plan(client, mc, env, today, end)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
        log.warning("meals tile unavailable: %s", e)
        tiles._note_error("meals", e)
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
    tiles._note_ok("meals", None)
    _cache[key] = (time.monotonic() + MEALS_TTL, result)
    return _with_rolled(result, rolled)


def _with_rolled(result: dict, rolled) -> dict:
    """The cached read with each dinner's ``rolled`` flag set from the CURRENT
    rolled set (it changes without the plan changing)."""
    days = []
    for d in result["days"]:
        dn = d["dinner"]
        days.append({"date": d["date"],
                     "dinner": ({**dn, "rolled": dn["id"] in rolled} if dn else None)})
    return {**result, "days": days}


def _fail(e: BaseException) -> dict:
    return {"ok": False, "error": _error_text(e), "needs_auth": _auth_failed(e)}


async def random_dinner(client, cfg, env: dict, date_str: object, today: dt.date,
                        rolled, replace_id: object = None) -> dict:
    """Plan a random dinner on ``date_str``. Returns ``{ok, entry_id?}`` or
    ``{ok: False, error, status}``.

    Empty day: plans a random recipe. With ``replace_id`` (a re-roll): that id
    must be a dinner this hub picked (in ``rolled``) and still be on that date;
    the new pick is made FIRST and the old one removed after, so a failure
    never leaves the day empty, and a failed removal rolls the new pick back."""
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
    try:
        existing = [d for d in await _plan(client, mc, env, day, day)
                    if _dinner(d) is not None]
        have = {d.get("id") for d in existing}
        if replace_id is None and existing:
            return {"ok": False, "status": 409, "error": "that day already has a dinner"}
        if replace_id is not None and replace_id not in have:
            return {"ok": False, "status": 409, "error": "that dinner is gone from the plan"}
        old_rid = next((_dinner(e)["recipe_id"] for e in existing
                        if e.get("id") == replace_id), None) if replace_id is not None else None
        for attempt in range(RANDOM_TRIES):
            r = await client.post(f"{mc['base']}/api/households/mealplans/random",
                                  json={"date": day.isoformat(), "entryType": "dinner"},
                                  headers=_headers(env), timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            new_id = body.get("id") if isinstance(body, dict) else None
            if not _is_int(new_id):
                raise ValueError("random reply has no entry id")
            # a re-roll that lands on the SAME recipe reads as "nothing happened":
            # undo that pick and draw again (a few tries; a one-recipe library
            # keeps the last pick rather than looping)
            same = old_rid is not None and body.get("recipeId") == old_rid
            if not same or attempt == RANDOM_TRIES - 1:
                break
            await client.delete(f"{mc['base']}/api/households/mealplans/{new_id}",
                                headers=_headers(env), timeout=TIMEOUT)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
        log.warning("meals random failed: %s", e)
        return {**_fail(e), "status": 502}
    if replace_id is not None:
        try:
            d = await client.delete(f"{mc['base']}/api/households/mealplans/{replace_id}",
                                    headers=_headers(env), timeout=TIMEOUT)
            d.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("meals re-roll: removing the old dinner failed: %s", e)
            try:   # undo the new pick so the day still shows ONE dinner, the old one
                await client.delete(f"{mc['base']}/api/households/mealplans/{new_id}",
                                    headers=_headers(env), timeout=TIMEOUT)
            except httpx.HTTPError:
                log.warning("meals re-roll: could not undo the new pick either")
            return {**_fail(e), "status": 502}
    _cache.clear()
    return {"ok": True, "entry_id": new_id}


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
    except ValueError as e:
        return {"ok": False, "error": str(e)[:120], "status": 409}
    except httpx.HTTPError as e:
        log.warning("meals add-to-shopping failed: %s", e)
        return {**_fail(e), "status": 502}
    return {"ok": True, "list": list_name}


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
    ctype = r.headers.get("content-type", "")
    if not ctype.startswith("image/"):
        return None
    if len(_image_cache) >= IMAGE_CACHE_MAX:
        _image_cache.pop(next(iter(_image_cache)))
    _image_cache[recipe_id] = (time.monotonic() + IMAGE_TTL, r.content, ctype)
    return r.content, ctype
