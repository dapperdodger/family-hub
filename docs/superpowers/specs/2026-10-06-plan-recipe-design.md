# Plan a recipe on a day: design

Mealie piece 3. Pieces 1 (Shopping card) and 2 (Recipes browser) shipped.

## Intent

On a recipe's page in the Recipes view, tap **Plan it**, pick a day, and that recipe becomes
that day's dinner on the Mealie meal plan. For the family at the wall and on phones. Done when the
Dinner card shows the recipe on the chosen day.

## Decisions (operator, 2026-10-06)

- **A hub pick is the dinner.** Planning a recipe on a day REPLACES every dinner already on that day,
  whether the hub rolled it or somebody planned it by hand. There are never two dinners from this action.
  (This reverses the old TODO rule "never replace a hand-planned dinner"; the random pick and Re-roll keep
  their own rules unchanged.)
- **No Re-roll.** The new dinner is NOT remembered as hub-picked, so the card offers no Re-roll for it.
- Dinner only. Only days the Dinner card shows (today through `mealie.days - 1`).

## Behaviour

`POST /api/mealie/plan` with `{recipe_id, date}`.

1. Validate: Meals configured (404), token set (503, `needs_auth`), `date` parses and is inside the shown days
   (422), `recipe_id` is a UUID (422).
2. Read the day's plan; collect its dinner entries.
3. If the day's only dinner is already this recipe: succeed without writing (`same: true`). This makes a
   double tap harmless.
4. Create the new dinner entry FIRST (`POST /api/households/mealplans`, `entryType: dinner`, `recipeId`),
   then delete each old dinner entry (404 on delete counts as gone). A failure creating leaves the day
   untouched. A failure deleting keeps the new dinner (it is what was asked for), and reports that the old one
   could not be removed so it can be removed in Mealie.
5. Drop the deleted entries from the hub's re-roll memory (`rolled`); never add the new one.
6. Always invalidate the cached plan. Runs under the existing meals write lock.
7. Reply `{ok, entry_id, recipe_id, same}` or `{ok: false, error, status}` with the same shape and error
   mapping as `/api/mealie/random`. Demo mode replies `{ok: true, demo: true}`.

## UI

- The recipe page gets a **Plan it** button (44px on the phone). It opens a row of day chips under the button:
  Tonight, Tomorrow, then weekday + date, one per day the card shows. Each chip also shows what is on that
  day now (its dinner name, or "Nothing planned"), so replacing something is never a surprise.
- Tapping a chip posts the plan, with every chip disabled while it is in flight (no double submit). Success: a
  toast ("Planned <recipe> for <day>"), the chip row closes, the Dinner card behind the overlay refreshes.
  Failure: the server's message in a toast and the chips stay.
- The days come from the data the Dinner card already holds. If that is not loaded, the button is hidden
  rather than guessing days.
- Everything from Mealie rendered as text, never HTML (as in the rest of the Recipes view).

## Out of scope

Breakfast/lunch slots, planning from the grid card (detail page only), undo, planning several days at once,
notes on an entry, serving counts.

## Verify against the real Mealie before building

The entry-create call (`POST /api/households/mealplans` body shape with `recipeId`) and the reply shape are
checked with a probe script the operator runs (token stays out of chat), as was done for the shopping list.

## Testing

Backend with the fake Mealie: empty day, one hand-planned dinner, several dinners, same recipe already there,
validation failures, create failure leaves the day alone, delete failure keeps the new dinner and says so,
re-roll memory cleared for removed entries and not set for the new one, plan cache invalidated. DOM tests: button
and chips, labels, in-flight disable, success and failure toasts, hidden when no days. Static guards for new CSS
classes, a changelog bullet, README and `docs/hub.png`, and the usual visual gates and three review passes.
