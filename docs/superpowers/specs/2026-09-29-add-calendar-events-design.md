# Add-event support for Google calendars — design

Source: "Phase 1: Fork and add events" in the family-hub project to-do doc.
Goal: let someone add an event from the wall/phone/tablet, written to the
right family member's real Google calendar, without waiting for the next
poll cycle to see it land.

## Scope

In scope (Phase 1 of the source doc):
- OAuth scope change so the app can write events, not just read them.
- `POST /api/events`: create a single, non-recurring event on a configured
  Google calendar.
- Frontend: a `+` button in the calendar overlay, an add-event modal
  (title, calendar/person picker, date, all-day toggle, start/end time,
  optional location/description).
- Tests, DEMO-mode support, changelog entry.

Explicitly out of scope (the source doc lists these under "Later"):
- Editing or deleting events from the wall.
- Recurring events.
- Writing to ICS-sourced calendars (those are read-only external feeds;
  the picker only offers `kind: "google"` calendars).

Not done by this feature (operator/manual steps, tracked separately):
- Google Cloud console project/OAuth-consent setup.
- Re-running `scripts/google-auth.py` to mint a token.json carrying the
  new scope, and copying it to the box.
- Making one Google calendar per family member (Phase 2 of the source doc).
- Opening an upstream issue on drench44/family-hub (deferred until this
  feature works, per the operator).

## OAuth scope

The source doc says "change the scope to `calendar.events`." That alone
is not sufficient: `calendar.events` covers the Events resource only, and
`GoogleCalendarClient.fetch_calendar_colors` already depends on
`calendarList.list`, which needs `calendar.readonly` (or broader). Scoping
down to just `calendar.events` would silently break calendar rail colors.

`SCOPES` in both `src/family_hub/calendar_sync.py` and
`scripts/google-auth.py` becomes:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
```

`google-auth.py`'s docstring/prompts get a one-line update: the browser
consent screen will now also ask for write access to events. Existing
`token.json` files do not carry the new scope, so the operator must re-run
the script and redeploy the token — the runbook for this ships in the PR
description, not in the app.

## Backend

### `GoogleCalendarClient.create_event`

New method alongside `fetch_events`/`fetch_calendar_colors`, same shape:

```python
def create_event(self, calendar_id: str, body: dict) -> dict:
    from googleapiclient.discovery import build
    service = build("calendar", "v3", credentials=self._creds(),
                    cache_discovery=False)
    return service.events().insert(calendarId=calendar_id, body=body).execute()
```

### `db.add_event_row`

`db.py` has `replace_events` (wholesale window replace per source) but no
single-row insert. Add:

```python
def add_event_row(conn, event: dict) -> None:
    """Insert or replace one cached event row (PK: calendar_id, id)."""
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO events(id, calendar_id, title, start_ts, "
            "end_ts, all_day, updated, location, description, color_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event["id"], event["calendar_id"], event["title"],
             event["start_ts"], event["end_ts"], event["all_day"],
             event.get("updated"), event.get("location", ""),
             event.get("description", ""), event.get("color_id")))
```

Used by both the DEMO path and the live path's immediate-visibility insert
(below). Reuses the exact column list `_replace_events` already writes, so
row shape stays consistent.

### `POST /api/events`

Request model:

```python
class EventIn(BaseModel):
    calendar_id: str
    title: str
    start: str                  # "YYYY-MM-DD" if all_day, else ISO datetime
    end: str | None = None      # defaults: +1 day (all-day) / +1 hour (timed)
    all_day: bool = False
    location: str = ""
    description: str = ""
```

Validation (422 on failure, same style as `_validate_todo`):
- `title` 1–200 chars after strip.
- `calendar_id` must match a configured calendar with `kind == "google"`
  (or the DEMO calendar id in DEMO mode). Anything else — unknown id, or a
  `kind: "ics"` calendar — is rejected with a clear message ("this
  calendar doesn't support adding events" for ICS, "unknown calendar" for
  a bad id).
- `start` must parse; `end` (if given) must be >= `start`.

Handler, DEMO branch:

```python
if DEMO:
    row = _event_row_from_input(merged)   # local normalize, no Google call
    fdb.add_event_row(c, row)
    return row
```

`config.demo.json` already declares one `kind: "google"` calendar
(`demo-home`), so the picker naturally offers exactly that one option in
DEMO mode — no demo-mode special-casing needed in the picker itself.

Handler, live branch:
1. Build the Google event body (`{"summary", "location", "description",
   "start": {"date": ...} | {"dateTime": ..., "timeZone": house_tz},
   "end": {...}}`).
2. If `client.configured()` is False: raise a distinct error the frontend
   can recognize as "not connected" (`needs_auth: true` in the response
   body, 409), matching how `calendar_status` already reports this state
   elsewhere — never a generic 500.
3. Call `client.create_event(...)`. Any exception becomes a clean
   `HTTPException(502, ...)` with the Google error message; never an
   unhandled raise (this repo has no global exception handler — a raise is
   a bare 500 on the wall).
4. Normalize the returned item via the existing `calendar_sync.
   normalize_event` and `fdb.add_event_row` it immediately, so the caller
   sees the new event in the response without waiting on step 5's network
   round trip.
5. Call `sync_once(GoogleCalendarClient(TOKEN_PATH), c, cfg, _now_local())`
   synchronously — the doc's "insert, then trigger a re-sync." This
   reconciles colors/other-calendar drift and is the same call the
   background thread already makes every 300s, so no new sync machinery.

No new integration-registry descriptor: `google_calendar`'s existing one
(`any(kind=="google")`) already gates this. The `+` button and picker hide
under the existing `body.integ-off-google_calendar` CSS rule — CLAUDE.md
is explicit that a feature must not build a second toggle mechanism.

No new secret/env var (reuses `TOKEN_PATH`), so no docker-compose /
`.env.example` change.

## Frontend

- A `+` button in the calendar overlay's nav row (next to Today/prev/next
  in `renderCalendar`), present on both wall and phone since they share
  the same responsive overlay markup.
- A new `add-event` modal, structurally modeled on the existing
  `ev-modal`/`openEventDetail` pattern: close button, `dialogOpened`/
  `dialogClosed`, participates in `wallBusy()`/idle-return, focus moves in
  on open and back on close. Reuses the existing modal's CSS/animation
  classes — no new animated classes, so no reduced-motion roster changes
  expected.
- Fields: title, calendar/person picker (`<select>` of `cfg.calendars`
  filtered to `kind === "google"`, each option showing label + a color
  swatch matching the calendar's rail color), date, all-day toggle,
  start/end time (hidden when all-day), optional location/description.
- Submit → `POST /api/events`. Success: close the modal, splice the
  returned event into the rendered calendar. Failure: inline error text in
  the modal (a `needs_auth` response renders "Calendar isn't connected —
  check Settings"; anything else renders the server's message) — never a
  bare `alert()`.
- Mobile: render the modal at ≤400px and confirm the `<select>`/text
  inputs behave correctly with `osk.js` (the on-screen keyboard); tap
  targets ≥44px. No tab-bar re-fit needed (no new tab — same overlay).

## Tests

Python:
- `create_event` happy path (mocked `googleapiclient`, same style as
  `test_google_client.py`'s existing `fetch_events` tests).
- `POST /api/events`: valid create (live path, mocked client), DEMO-mode
  create (no client involved), unknown `calendar_id` (422), `kind: "ics"`
  calendar_id (422), missing/invalid title (422), `end < start` (422),
  not-configured client (409 + `needs_auth`), Google API failure (502, not
  a bare 500).
- Run both suites under `TZ=UTC` per the gauntlet's standing requirement.

JS (fake-DOM):
- Modal open/close, focus handling, `dialogOpened`/`dialogClosed` wiring.
- Picker populated from `cfg.calendars` (google-kind only, ICS excluded).
- Form validation (empty title, end before start).
- Success path splices the new event into the render; error path shows
  the inline message, not a thrown exception.
- `escapeHtml` on every user-entered string (title/location/description)
  rendered back into the DOM.

Static guards (`test_static.py`): confirm the `+` button/modal are wired
under the same `integ-off-google_calendar` hook as the rest of the
calendar surface — no second toggle mechanism.

## Docs & release

- README: one bullet under "What it looks like" for add-event.
- Regenerate `docs/hub.png` from `DEMO=1` at 1920px (the calendar overlay
  open, `+` button visible).
- `CHANGELOG.md`: new `## [Unreleased]` / `### Added` entry (CI's
  `changelog-guard` and the local pre-commit hook both require this for
  any `src/**` change).
- No `config.example.json` or `.env.example` change (no new config shape,
  no new secret).
- Version bump / `scripts/release.py` is NOT run as part of this
  implementation — that's a deploy-readiness decision for the operator
  once they've re-authed with the new scope and confirmed on real
  hardware.

## Review gate

Per CLAUDE.md: run all three `pr-review-toolkit` agents
(`silent-failure-hunter`, `code-reviewer`, `pr-test-analyzer`) on the
branch diff before merge, including a re-run if the branch grows after
the first pass. Now installed and confirmed available in this session.

## Visual gates — what needs the operator

This session can run the DEMO server and take screenshots (full desktop
width, phone width, themes, night mode, the modal open) as part of the
gauntlet's visual-gate checklist. It cannot verify: the physical wall
panel's gamma/contrast, a real iPhone (required for anything
mobile/modal-related per CLAUDE.md's iOS Safari section), or Firefox ESR
rendering. Those stay checks the operator confirms before calling this
done.
