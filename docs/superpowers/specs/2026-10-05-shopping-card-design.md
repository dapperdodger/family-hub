# Shopping card (Mealie shopping list on the wall) — design

Piece 1 of three native Mealie views. The Meals card (PR #4/#5) already shows
tonight's dinner and the week from Mealie and can add a recipe's ingredients to
the shopping list. Opening Mealie itself in the full-screen iframe is slow on a
Raspberry Pi 3 (a 15-25 s blank page: Mealie is a heavy single-page app), and the
operator only uses a small part of Mealie on the wall. The three pieces replace
that iframe with native hub views:

1. **Shopping card with quick add** (this spec).
2. Recipe browser: photo grid, search on the on-screen keyboard, category chips,
   recipe detail (ingredients and steps). Own spec.
3. Assign a recipe to a day on the meal plan (dinner slot). Own spec.

## Goal

A "Shopping" card on the wall, and a Shopping section on the phone's Meals tab,
that shows the Mealie shopping list, lets someone check items off and un-check
them, add a free-text item quickly, and delete an item. Light enough for a Pi 3.

## Scope

In scope:
- Read the configured Mealie shopping list (the `mealie.shopping_list` setting,
  an id or a name; otherwise the first list), trimmed to what the card shows.
- Check / un-check an item.
- Quick add: a free-text item.
- Delete an item.
- Wall card, phone section, DEMO payload, fail-soft states, tests, changelog,
  README + `docs/hub.png`.

Out of scope (deliberately, no creep):
- Editing an item's quantity or text; units, foods, labels or aisle grouping.
- More than one list (the single configured list only).
- The recipe browser and meal-plan assignment (pieces 2 and 3).
- Removing or changing the To-Do feature. To-Dos stays; the operator can switch
  it off with its existing Settings toggle (`todos` in the integration registry).
- Changing how the existing "add a recipe's ingredients" endpoint works.

## Mealie API (verified against v3.28.0's `/openapi.json`)

- `GET /api/households/shopping/lists` (already used by `_shopping_list`).
- `GET /api/households/shopping/items` (paged; filter by list),
  `POST /api/households/shopping/items`,
  `GET|PUT|DELETE /api/households/shopping/items/{item_id}`.
- An item carries `note` (free text), `checked`, `quantity`, `unit`, `food`,
  `display`, `position`, `shoppingListId`. Create and update both require
  `shoppingListId`. A recipe-derived item has a `food` and `display`; a free-text
  item has just `note`.
- The exact filter syntax for listing a list's items and the display text to
  show for a recipe-derived item (`display` vs `note`) are checked against the
  live server while writing the plan, not guessed here.

## Backend (`meals.py`, `app.py`)

All of it follows the existing meals pattern: the token comes only from the
environment, every read fails soft, writes return `{ok, error?, status?}` and
never raise, and every id that goes into an upstream URL path is validated
(`valid_uuid`).

- `GET /api/mealie/shopping` -> `{available, list: {id, name}, items: [{id,
  text, checked}]}`. Trimmed, capped (like `MAX_PLAN_ITEMS`), unchecked first,
  then checked. A dead or misbehaving Mealie is `{available: false}`, never an
  exception. A rejected token sets the same `needs_auth` state the Meals card
  uses. Cached briefly; every write bumps the cache generation, so a read that
  began before a write can't cache its pre-write answer (the `_gen` pattern).
- `POST /api/mealie/shopping/items` `{text}` -> adds a free-text item (`note`) to
  the configured list. Text is trimmed, non-empty, length-capped.
- `PUT /api/mealie/shopping/items/{id}` `{checked: bool}` -> Mealie's update
  needs the whole item, so the server reads the item, sets `checked`, writes it
  back. It first confirms the item belongs to the configured list; an id from
  another list or another household is a 404, not a write.
- `DELETE /api/mealie/shopping/items/{id}` -> same list-membership check first.
- Writes that change the same list serialize behind a lock (single process, a
  plain asyncio lock, like `_meals_write_lock`), so two phones tapping at once
  can't interleave a read-modify-write.
- DEMO mode returns a canned list for the read and `{ok: true, demo: true}` for
  the writes, with no Mealie call. A demo write must not mutate anything.
- The shopping read is part of `/health/full`'s `meals` source (no new source:
  it is the same Mealie and the same token). A failing shopping read does not
  turn the dinner tile red.

## Frontend (`hub.js`, `styles.css`)

Follows the To-Do card and the Meals card; reuses their patterns instead of
inventing new ones.

- **Wall card.** Header "Shopping" with the open-item count. Under it a quick-add
  field (tap it, type with the hub's on-screen keyboard, Add). Under that the
  list: unchecked items first, tap a row to check it; checked items sit below,
  dimmed and struck through, tap to un-check.
- **The list scrolls inside the card, like the meal plan.** The rows live in a
  container with a height cap (it shows several rows and the top of the next, the
  peek being the hint there is more), `overflow-y: auto`,
  `overscroll-behavior: contain`, `scrollbar-width: thin`, and
  `-webkit-overflow-scrolling: touch`. The quick-add field stays put above the
  scrolling region, so a long list never makes the column taller than the screen.
  The phone shell lifts the cap (the Meals tab is its own scrolling page), exactly
  as `.meal-rows` does today.
- **Row actions.** Tapping an item's text (not its check) opens an action row
  inline under it with **delete**; checking is one tap, deleting two, so it is
  hard to do by accident. Inline, not a popover: a floating popover would be
  clipped by the scrolling list (the same reason the meal-row menu is inline).
  Open menu closes on a second tap, another row, or a write.
- **Placement.** The card sits in the wall's To-Do slot position. The existing
  `integ-off-todos` mechanism hides To-Dos when the operator switches it off, and
  the Shopping card takes the space. The plan must verify the wall layout with
  To-Dos on AND off, since the wall is a fixed 1920 px layout.
- **Phone.** The Meals tab gets a Shopping section under the dinner card, same
  actions; 44 px tap targets, clear of the home-indicator zone, nothing
  `position: fixed`, no `backdrop-filter` (see CLAUDE.md's iOS traps).
- **Responsiveness.** Checking updates the screen immediately and rolls back with
  an error message if Mealie refuses. The card re-reads about once a minute and
  after its own writes; fetches use the existing newest-wins pattern, so a slow
  older response can't overwrite a newer one. Keyboard focus is restored after a
  re-render (the `mealsRestoreFocus` pattern).
- **Failure states.** Mealie down: a quiet "couldn't load" note, last list kept.
  Token rejected: the same needs-auth state as the Meals card. An empty list has
  its own empty state, not a blank card.
- **Motion.** Transform/opacity only, paused under `prefers-reduced-motion`,
  nothing that animates continuously (cheap on a Pi 3).
- **Registry.** The Shopping card follows the `mealie` integration's on/off
  (no separate toggle unless the plan finds one is needed); it appears only when
  Mealie is configured.

## Tests and gates

Per `docs/adding-a-feature.md`, every gate, in order. For this feature
specifically:
- `tests/test_meals.py`: read trimming and capping, cache + generation
  invalidation, each write's validation (bad uuid, empty text, over-long text,
  item from another list), fail-soft on a dead Mealie, needs-auth on a 401/403,
  the read-modify-write really sends the whole item with only `checked` changed,
  the write lock.
- `tests/test_demo.py`, `tests/test_integrations.py`, `tests/test_health_full.py`
  as the new payload and source touch them.
- `tests/js/hub-dom.test.mjs`: render, optimistic check + rollback, quick add,
  the inline delete menu, newest-wins, focus restore, scroll container present.
- `tests/test_static.py`: a guard that the list container is the scroller
  (height cap + `overflow-y: auto` + `overscroll-behavior: contain`) and that the
  phone shell lifts the cap; no `backdrop-filter` on fixed elements.
- Visual gates: wall at full 1920 px, mobile at <= 400 px, night, all five
  themes, seasons off and on, To-Dos on and off, a long list and an empty one.
- Three-agent review, CHANGELOG entry, README and `docs/hub.png` regenerated in
  the same PR, live post-deploy check on the real wall.

## Open items for the plan

- Confirm the item-list filter syntax and which text field to show for a
  recipe-derived item against the live Mealie.
- Decide the card's row budget and height cap (target: about four rows and a
  peek, matching the meal plan, tuned on the 1920 px wall).
- Confirm the layout when To-Dos is switched off.
- Measure the card on a Pi 3 kiosk once built (the operator's wall display).
