# Recipe browser (native Mealie recipes view) — design

Piece 2 of three native Mealie views (piece 1: the Shopping card, shipped; piece 3: put a
recipe on a day of the meal plan, own spec). Opening Mealie itself in the Dinner card's
"Full screen" iframe is a 15-25 s blank page on a Raspberry Pi 3 (Mealie is a heavy
single-page app; its server answers in ~40 ms, so the cost is the Pi running it). The
operator only uses a small part of Mealie on the wall, so this replaces the iframe with a
native, light view of the part they use: finding a recipe and reading it.

## Goal

A full-screen **Recipes** view, on the wall and on the phone, that lists the Mealie recipes
as a photo grid, lets someone search, filter by category and sort, and open one to read its
ingredients, steps and notes. Fast on a Pi 3, usable by touch with no keyboard, readable
from across a kitchen.

## Scope

In scope:
- Grid of all recipes (photo, name, total time), search, category chips, sort buttons.
- A recipe detail view: photo, prep/cook time, servings, description, ingredients, steps,
  then notes. Back button; the grid's search/sort/category/scroll are restored on Back.
- Two read-only hub endpoints (list, detail) and a size option on the existing photo proxy.
- Entry points: the Dinner card's button (wall) and a Recipes button on the phone's Meals tab.
- Demo-mode data, fail-soft states, tests, changelog, README + `docs/hub.png`.

Out of scope (deliberately):
- Planning a recipe onto a day (piece 3), adding its ingredients to the shopping list from
  the detail view, servings scaling, nutrition, ratings display/editing, sources, comments.
- Recipe import, editing, deleting, favourites; any Mealie admin.
- Searching by ingredient (the list endpoint carries no ingredients).
- Sorting by time (Mealie stores times as free text such as "1 Hour 30 Minutes").
- A link back to Mealie itself (the old `open_url` button target). The config key stays valid
  and is documented as unused by the button, so existing configs do not break.

## Decisions made with the operator

- Library is under 50 recipes today, could reach 100+: load every summary in ONE request and
  filter/sort on the screen (instant, no server round trip per keystroke). Server caps the
  list at 200 and flags `truncated`; no paging until someone outgrows it.
- Default order A to Z. Sort buttons: **A to Z**, **Recently added**, **Recently made**
  (recipes never made last), **Top rated** (unrated last). Ties fall back to A to Z.
- Detail shows the basics plus notes only (no nutrition, no scaling, no source/rating).
- One overlay view with its own list/detail navigation (not a pop-up over the grid).
- Wall: the Dinner card's "Full screen" button becomes **Recipes** and opens this view.
  Phone: a **Recipes** button on the Meals tab opens the same view.

## Mealie API (verified against v3.28.0's `/openapi.json`)

- `GET /api/recipes` takes `search`, `categories`, `tags`, `orderBy`, `orderDirection`, `page`,
  `perPage`, `queryFilter` and more, and returns `{page, per_page, total, total_pages, items}`
  of `RecipeSummary`: `id`, `name`, `slug`, `image` (string or null), `totalTime`, `prepTime`,
  `cookTime` (strings or null), `recipeServings`, `description`, `rating` (number or null),
  `lastMade`, `dateAdded` (strings or null), `recipeCategory`, `tags` (arrays of
  `{id, name, slug}`).
- `GET /api/recipes/{slug}` returns the full recipe: the summary fields plus `recipeIngredient`
  (items with a computed `display`, a `note`, and an optional section `title`),
  `recipeInstructions` (steps with `title`, `summary`, `text`) and `notes` (`title`, `text`).
- Photos: `GET /api/media/recipes/{recipe_id}/images/{file_name}`; the hub already proxies
  `min-original.webp`. **Verified on the operator's server (2026-10-06, one recipe):**
  `tiny-original.webp` exists (HTTP 200, 600x600 square crop, 88 KB), `min-original.webp`
  is 683x1024 (145 KB) and `original.webp` is 1024x1536 (290 KB). "Tiny" is therefore not
  small: a grid card is about 250 px wide and a screenful (about 24 cards) is roughly 2 MB.
  Fine over the LAN; the Pi 3's decode cost is the thing to measure. Mealie has no smaller
  size. If the Pi 3 struggles, the follow-up is for the hub to downscale thumbnails itself,
  which needs an image library the hub does not have (not part of this feature unless the
  measurement says so). Grid cards use `tiny`, the detail view uses `min`; if a recipe has
  no `tiny` the proxy falls back to `min`.

## Backend (`meals.py`, `app.py`)

Same pattern as the Shopping card: token only from the environment, every read fails soft
(`{available: false}`, never an exception), validated ids in URL paths, a short cache.

- `GET /api/mealie/recipes` -> `{available, needs_auth?, truncated, total, recipes: [{slug, id,
  name, time, has_image, categories: [name], tags: [name], added, made, rating}]}`. Names are
  trimmed and length-capped; unusable entries (no slug or name) are skipped and counted in a
  warning log. One upstream request (`perPage` 200, ordered by name). Cached ~5 minutes.
  A reply without an items list is `{available: false}`, never an empty library.
- `GET /api/mealie/recipes/{slug}` -> `{available, needs_auth?, recipe: {slug, id, name,
  has_image, servings, prep, cook, total, description, ingredients: [{text} | {heading}],
  steps: [{title?, text}], notes: [{title?, text}]}}`. All text trimmed and length-capped, plain
  text only (the view never renders Mealie's markdown or HTML). Ingredient text prefers
  Mealie's `display`; section titles become headings. Cached per slug, bounded (LRU ~32).
  An unknown slug is a clean 404.
- The slug goes into an upstream URL, so it must match Mealie's slug shape (lowercase letters,
  digits, hyphens, bounded length) before any request.
- `GET /api/mealie/image/{recipe_id}?size=tiny|min` (default `min`, today's behaviour).
  Unknown sizes are a 422. Cached per (id, size) in the existing bounded image cache.
- Read-only: no writes, so no cache invalidation beyond the TTL. A rejected token sets the
  same shared `auth_rejected` flag the Meals/Shopping reads use and never turns the dinner
  tile red on its own.
- Demo mode returns a canned library (about 12 recipes across 4 categories, with and without
  photos, notes, sections) and a canned detail; no Mealie call.

## Frontend (`hub.js`, `styles.css`)

A new overlay view `recipes` through the existing `openOverlay` / `closeOverlay`, so it
inherits the idle return, `wallBusy`, Escape and the home pill. It rides the Meals (Mealie)
integration switch (no new toggle).

- **Grid screen.** Search box (class `txt-input`, so the wall's on-screen keyboard serves it),
  the four sort buttons, category chips (**All** first, then each category by name), then the
  cards: small thumbnail (lazy, `decoding=async`), name (two lines, ellipsized), total time.
  About six across on the wall, two on the phone. Search matches name, categories and tags,
  case-insensitively; a chip and the search combine; the sort applies to the result.
- **Detail screen.** Replaces the grid in the same overlay with a Back button. Wall: photo +
  meta (times, servings, description) on the left, ingredients then numbered steps on the
  right, then notes. Phone: one column. Large text (about 18px on the wall).
- **State.** Search text, sort, category and the grid's scroll position live in module state
  and are restored on Back. Opening the view fetches the list (newest-wins numbering, like
  the Shopping fetch); tapping a card fetches its detail with the same guard.
- **Typing never repaints the search box.** Filtering redraws only the card area, so the
  keyboard keeps focus (the Shopping card's lesson).
- **States.** Loading, "Mealie isn't reachable", "Needs a Mealie token", "No recipes match",
  an empty library, and a quiet "showing the first 200 of N" note when truncated. A failed
  detail fetch keeps the grid and shows a toast with a retry on tap.
- **Idle return.** `idleReturnMs('recipes')` is 15 minutes (the default 90 s would close a
  recipe someone is cooking from; cameras get 5 minutes, the calendar 3).
- **Performance on a Pi 3.** No `backdrop-filter`, no animation, thumbnails not full photos,
  at most 200 cards, nothing that runs on a timer.
- **Phone.** The Meals tab gets a Recipes button; the same overlay fills the screen; 44 px
  tap targets; nothing `position: fixed` with `backdrop-filter`; no transform on fixed
  interactive elements (CLAUDE.md's iOS traps).
- **Removal.** The `meals-full` iframe branch of `openOverlay` and its Settings/README text go;
  `open_url` stays in config cleaning (accepted, documented as unused by the button).

## Tests and gates

Per `docs/adding-a-feature.md`, every gate, in order. For this feature specifically:
- `tests/test_meals.py`: list trimming/capping/skipping, `truncated`, the no-items-list case,
  cache TTL, 401/403 vs 500 vs transport errors, wrong-shaped bodies (never raises); detail
  trimming, sections/headings, markdown and HTML left as inert text, bad and unknown slugs
  (no request for a bad one, 404 for an unknown one), per-slug cache bound; image size
  whitelist and cache keying; token/config refusals make no request.
- `tests/test_demo.py`, `tests/test_integrations.py`, `tests/test_health_full.py` as the
  payload and routes touch them.
- `tests/js/hub-dom.test.mjs`: filter + sort + chip combinations (including never-made and
  unrated ordering), search matching, the keyboard-focus carry while typing, Back restoring
  state, newest-wins for list and detail, the failure states, XSS of every Mealie string.
- `tests/test_static.py`: the overlay view is wired, the Meals switch hides the button, the
  `txt-input` class, the phone button, no `backdrop-filter`/animation in the new CSS, and
  `idleReturnMs('recipes')` is longer than the default.
- Visual gates (all five themes, night, seasons on/off, the phone at 390 and 360 px), the
  three-agent review, CHANGELOG, README and `docs/hub.png` in the same PR, and a live check
  on the real wall and the Pi 3 (the point of the feature is that it loads fast).

## Open items for the plan

- Confirm what `image` holds on the live Mealie (a hash string) so `has_image` is computed
  correctly. (`tiny-original.webp` is confirmed: see the photos note above.)
- Confirm how Mealie writes `totalTime` (free text) so the card shows it as given.
- Decide the card grid breakpoints (six across on the 1920 wall, two on a phone) and the
  detail text sizes on the real wall.
- Measure the list payload size with the real library and the time to first paint on the Pi 3.
