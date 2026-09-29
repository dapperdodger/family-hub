# Add-event support for Google calendars — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let someone create a single, non-recurring event on a real Google
calendar from the wall/phone/tablet calendar overlay, with the new event
visible immediately.

**Architecture:** A new `POST /api/events` endpoint validates and writes
through the existing `GoogleCalendarClient` (extended with `create_event`),
inserts the normalized row locally for instant feedback, then re-runs the
existing `sync_once` reconciliation. DEMO mode writes straight to the local
`events` table (no Google account exists in DEMO). The frontend adds a `+`
button to the existing calendar overlay's nav row, opening a new modal built
from a reusable form (mirroring the existing chore-editor pattern).

**Tech Stack:** FastAPI + SQLite (Python), vanilla JS (no build step, no
npm), `googleapiclient`/`google-auth-oauthlib` for the Google Calendar API,
`pytest` for Python tests, Node's built-in `node --test` for JS tests.

**Spec:** `docs/superpowers/specs/2026-09-29-add-calendar-events-design.md`

## Global Constraints

- No new integration-registry descriptor — reuse `google_calendar`'s
  existing one. Correction from the design spec: `google_calendar` is
  `group="integration"` (`kind="calendar"`), not one of the `group="feature"`
  core surfaces (chores/todos) that get a dedicated `body.integ-off-<id>`
  CSS hide rule — there is no such rule for calendar, since the Calendar
  overlay is always present and the source toggles (`google_calendar`,
  `ics_calendar`, `icloud_caldav`) already gate by filtering which events
  populate it (`_calendar_block`'s `cal_google_on` etc.), not by hiding a
  DOM slot. The `+` button/modal follow that SAME existing pattern: Task 4's
  `_writable_calendars` already returns `[]` when `google_calendar` is off,
  and Task 7's `buildAddEventForm` already renders "no calendar configured"
  instead of a picker when the list is empty — no CSS hook, no second
  toggle mechanism, no new registry descriptor.
- OAuth scopes become BOTH `calendar.readonly` and `calendar.events` (not
  `calendar.events` alone) — `fetch_calendar_colors`'s `calendarList.list`
  call needs `calendar.readonly`.
- No new secret/env var; reuse `TOKEN_PATH`.
- DEMO mode (`DEMO=1`) must support add-event with NO real Google account
  (writes straight to the local `events` table against the `demo-home`
  calendar `config.demo.json` already declares).
- Every server-side failure becomes a clean `HTTPException` — this repo
  has no global exception handler, so an uncaught raise is a bare 500 on
  the wall.
- Every new JS string interpolated into markup goes through `escapeHtml`.
- `CHANGELOG.md` needs a new `## [Unreleased]` / `### Added` line — CI's
  `changelog-guard` and the local pre-commit hook both block a PR that
  touches `src/**` without one.
- Run the Python suite under both default and `TZ=UTC` environments per
  CLAUDE.md's standing rule for time-formatting tests.
- Before merge: run all three `pr-review-toolkit` agents
  (`silent-failure-hunter`, `code-reviewer`, `pr-test-analyzer`) on the
  branch diff, and re-run if the branch grows after the first pass.

## Review Focus

- **Double-submit:** a fast double-tap on the modal's submit button must
  not fire two `POST /api/events` (mirrors the existing `oneSaveAtATime`
  guard used by the chore editor) — tested in Task 8.
- **All-day end-date exclusivity:** picking a single all-day date must
  send an `end` one day AFTER `start` (Google's exclusive-end convention),
  not the same date — tested in Task 5 (server default) and Task 7
  (`buildEventPayload`).
- **Server-side calendar_id trust:** a stale or tampered frontend request
  naming an ICS/CalDAV calendar_id (not just an unknown one) must be
  rejected server-side even though the picker already filters — tested in
  Task 5.
- **XSS through the new write path:** `submitAddEvent` must not pre-escape
  or hand-splice the created event's title into any markup itself — it
  must store the RAW row into `evIndex`/`calWin.events` and let the
  already-tested render sinks (`monthWeekHtml`/`agendaHtml`'s
  `escapeHtml` calls, pinned by the existing "safeColor is applied at the
  color sinks" test) do the one real escaping pass. A double-escape or a
  bypassed sink are both caught by pinning the raw value survives into the
  index unmodified — tested in Task 8.
- **Write failure keeps the form open:** a network/server failure on
  submit must leave the modal open with the typed data intact and show an
  inline error, never silently discard what the user typed — tested in
  Task 8.

---

## File Structure

- `src/family_hub/calendar_sync.py` — modify: `SCOPES`, add
  `GoogleCalendarClient.create_event`.
- `scripts/google-auth.py` — modify: `SCOPES`, docstring.
- `src/family_hub/db.py` — add: `add_event_row`.
- `src/family_hub/app.py` — modify: `_calendar_block` (add `calendars` to
  its return), add `EventIn`, `_validate_event_calendar`,
  `_event_start_end`, `_event_google_body`, `events_add` (`POST
  /api/events`).
- `src/family_hub/web/static/hub.js` — modify: `calNavHtml` (add button),
  add `openAddEventModal`, `closeAddEventModal`, `submitAddEvent`; modify
  `MODAL_CLOSERS`, the click-delegation handler, the Escape-key handler.
- `src/family_hub/web/static/common.js` — add: `freshEventModel`,
  `buildEventPayload`, `buildAddEventForm`.
- `src/family_hub/web/static/index.html` — add: the `#add-event-modal`
  markup.
- `src/family_hub/web/static/styles.css` — add: `.add-event-modal` block.
- `tests/test_google_client.py`, `tests/test_db.py`, `tests/test_api.py`,
  `tests/test_static.py`, `tests/js/hub.test.mjs`, `tests/js/hub-dom.test.mjs`
  — new tests per task.
- `CHANGELOG.md`, `README.md` — release notes / feature bullet.

---

### Task 1: OAuth scope

**Files:**
- Modify: `src/family_hub/calendar_sync.py:24`
- Modify: `scripts/google-auth.py:2-25`
- Test: `tests/test_google_client.py`

**Interfaces:**
- Produces: `calendar_sync.SCOPES: list[str]` (now two entries), consumed
  by `GoogleCalendarClient` (Task 2) and read directly by
  `scripts/google-auth.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_google_client.py`:

```python
def test_scopes_include_both_readonly_and_events():
    """calendar.events alone would break fetch_calendar_colors, which needs
    calendarList.list (calendar.readonly). Both scopes must be requested."""
    from family_hub.calendar_sync import SCOPES
    assert "https://www.googleapis.com/auth/calendar.readonly" in SCOPES
    assert "https://www.googleapis.com/auth/calendar.events" in SCOPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_google_client.py::test_scopes_include_both_readonly_and_events -v`
Expected: FAIL (`calendar.events` not in SCOPES — the module currently
only carries `calendar.readonly`)

- [ ] **Step 3: Update the scope lists**

In `src/family_hub/calendar_sync.py`, replace:

```python
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
```

with:

```python
# Both scopes are needed: calendar.readonly covers calendarList.list (the
# user's own calendar colors, fetch_calendar_colors below); calendar.events
# covers events().insert (create_event) but NOT calendarList — scoping down
# to calendar.events alone would silently break the colors fetch.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
```

In `scripts/google-auth.py`, replace:

```python
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
```

with:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
```

and update the module docstring's `A browser opens; approve read-only
Calendar access.` line to:

```
A browser opens; approve Calendar access (read your calendars and create
events on them). This writes `token.json` here and prints the scp command
to copy it onto the box's data dir.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_google_client.py::test_scopes_include_both_readonly_and_events -v`
Expected: PASS

- [ ] **Step 5: Run the full existing calendar_sync/google_client test files to confirm no regression**

Run: `pytest tests/test_calendar.py tests/test_google_client.py -v`
Expected: PASS (SCOPES isn't asserted-equal anywhere else — these tests
mock the API surface, not the scope list)

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/calendar_sync.py scripts/google-auth.py tests/test_google_client.py
git commit -m "feat: request calendar.events scope alongside calendar.readonly"
```

---

### Task 2: `GoogleCalendarClient.create_event`

**Files:**
- Modify: `src/family_hub/calendar_sync.py` (after `fetch_events`, ~line 350)
- Test: `tests/test_google_client.py`

**Interfaces:**
- Consumes: `GoogleCalendarClient._creds()` (existing, unchanged).
- Produces: `GoogleCalendarClient.create_event(self, calendar_id: str,
  body: dict) -> dict` — returns the Google API's created-event resource
  (a dict with at least `id`, `summary`, `start`, `end`). Consumed by
  Task 5's endpoint.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_google_client.py`:

```python
def test_create_event_inserts_and_returns_the_created_item():
    svc = _fake_service()
    created = {"id": "new1", "summary": "Dentist",
               "start": {"dateTime": "2026-10-01T09:00:00-07:00"},
               "end": {"dateTime": "2026-10-01T10:00:00-07:00"}}
    svc.events.return_value.insert.return_value.execute.return_value = created
    with mock.patch("googleapiclient.discovery.build", return_value=svc), \
         mock.patch.object(GoogleCalendarClient, "_creds", return_value="creds"):
        body = {"summary": "Dentist",
                "start": {"dateTime": "2026-10-01T09:00:00-07:00", "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": "2026-10-01T10:00:00-07:00", "timeZone": "America/Los_Angeles"}}
        result = GoogleCalendarClient("/tmp/tok.json").create_event("cal1", body)
    assert result == created
    svc.events.return_value.insert.assert_called_once_with(calendarId="cal1", body=body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_google_client.py::test_create_event_inserts_and_returns_the_created_item -v`
Expected: FAIL with `AttributeError: 'GoogleCalendarClient' object has no attribute 'create_event'`

- [ ] **Step 3: Implement**

In `src/family_hub/calendar_sync.py`, add this method to
`GoogleCalendarClient`, directly after `fetch_events`:

```python
    def create_event(self, calendar_id: str, body: dict) -> dict:
        """Insert one event via events().insert. No pagination (a single
        insert), unlike fetch_events/fetch_calendar_colors above."""
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=self._creds(),
                        cache_discovery=False)
        return service.events().insert(
            calendarId=calendar_id, body=body).execute()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_google_client.py::test_create_event_inserts_and_returns_the_created_item -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/family_hub/calendar_sync.py tests/test_google_client.py
git commit -m "feat: add GoogleCalendarClient.create_event"
```

---

### Task 3: `db.add_event_row`

**Files:**
- Modify: `src/family_hub/db.py` (after `replace_events_caldav`, ~line 911)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `db.add_event_row(conn, event: dict) -> None` — `event` needs
  keys `id, calendar_id, title, start_ts, end_ts, all_day`, with
  `updated`, `location`, `description`, `color_id` optional. Consumed by
  Task 5's endpoint (both the DEMO and live branches).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_add_event_row_inserts_and_is_readable(conn):
    fdb.add_event_row(conn, {
        "id": "e1", "calendar_id": "cal", "title": "Dentist",
        "start_ts": "2026-10-01T09:00:00", "end_ts": "2026-10-01T10:00:00",
        "all_day": 0,
    })
    rows = fdb.list_events(conn)
    assert len(rows) == 1
    assert rows[0]["title"] == "Dentist"
    assert rows[0]["location"] == ""       # default applied, not NULL


def test_add_event_row_replaces_on_same_calendar_and_id(conn):
    fdb.add_event_row(conn, {"id": "e1", "calendar_id": "cal", "title": "Old",
                             "start_ts": "2026-10-01T09:00:00",
                             "end_ts": "2026-10-01T10:00:00", "all_day": 0})
    fdb.add_event_row(conn, {"id": "e1", "calendar_id": "cal", "title": "New",
                             "start_ts": "2026-10-01T09:00:00",
                             "end_ts": "2026-10-01T10:00:00", "all_day": 0})
    rows = fdb.list_events(conn)
    assert len(rows) == 1 and rows[0]["title"] == "New"


def test_add_event_row_leaves_other_calendars_untouched(conn):
    fdb.replace_events(conn, [{"id": "keep", "calendar_id": "other",
                              "title": "Keep me", "start_ts": "2026-10-01",
                              "end_ts": "2026-10-02", "all_day": 1}])
    fdb.add_event_row(conn, {"id": "e1", "calendar_id": "cal", "title": "New",
                             "start_ts": "2026-10-01T09:00:00",
                             "end_ts": "2026-10-01T10:00:00", "all_day": 0})
    ids = {(r["calendar_id"], r["id"]) for r in fdb.list_events(conn)}
    assert ids == {("other", "keep"), ("cal", "e1")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py::test_add_event_row_inserts_and_is_readable -v`
Expected: FAIL with `AttributeError: module 'family_hub.db' has no attribute 'add_event_row'`

- [ ] **Step 3: Implement**

In `src/family_hub/db.py`, add directly after `replace_events_caldav`:

```python
def add_event_row(conn, event: dict) -> None:
    """Insert or replace ONE cached event row (PK: calendar_id, id) — the
    single-row counterpart to replace_events's wholesale window swap. Used
    by the add-event endpoint for both DEMO's local-only write and the live
    path's immediate-visibility insert (ahead of the full resync)."""
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -k add_event_row -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Commit**

```bash
git add src/family_hub/db.py tests/test_db.py
git commit -m "feat: add db.add_event_row for single-row event upserts"
```

---

### Task 4: `_calendar_block` exposes writable calendars

**Files:**
- Modify: `src/family_hub/app.py:473-625` (`_calendar_block`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `cfg.calendars` (existing), `fdb.kv_get(c, "calendar_colors")`
  (existing), `fdb.integration_enabled` (existing).
- Produces: `_calendar_block(...)` return dict gains a `"calendars"` key:
  `list[{"id": str, "label": str, "color": str}]` — every configured
  `kind == "google"` calendar that isn't hidden by the `google_calendar`
  toggle, color-resolved the same way event rows already are (the user's
  synced Google color wins, config color is the pre-sync fallback).
  Consumed by the frontend's add-event picker (Task 8).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py` near the other `/api/calendar` tests (after
`test_google_calendar_color_beats_config`):

```python
def test_calendar_endpoint_lists_writable_google_calendars(client, app_mod):
    out = client.get("/api/calendar").json()
    assert out["calendars"] == [{"id": "cal", "label": "Fam", "color": "#5BC9F0"}]


def test_calendar_endpoint_calendars_list_prefers_synced_color(client, app_mod):
    c = app_mod._db()
    fdb.kv_set(c, "calendar_colors", {"cal": "#9FE1E7"})
    out = client.get("/api/calendar").json()
    assert out["calendars"][0]["color"] == "#9FE1E7"


def test_calendar_endpoint_calendars_list_hides_when_google_off(client, app_mod):
    c = app_mod._db()
    fdb.set_integration_enabled(c, "google_calendar", False)
    out = client.get("/api/calendar").json()
    assert out["calendars"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -k writable_google_calendars -v`
Expected: FAIL with `KeyError: 'calendars'`

- [ ] **Step 3: Implement**

In `src/family_hub/app.py`, inside `_calendar_block` (the function
defined at line 473), add a small helper directly above it and call it
from the return statement:

```python
def _writable_calendars(cal_google_on: bool, google_colors: dict) -> list[dict]:
    """Google-kind calendars this hub can write to (Task 4): every
    configured kind=='google' entry, hidden entirely when the integration
    toggle is off (same gating _calendar_block already applies to its
    events). Color prefers the user's synced Google color over the config
    fallback, matching every event row's own color resolution above."""
    if not cal_google_on:
        return []
    return [
        {"id": cal["id"], "label": cal.get("label", cal["id"]),
         "color": google_colors.get(cal["id"]) or cal.get("color", "")}
        for cal in cfg.calendars if cal.get("kind", "google") == "google"
    ]
```

Then change the `return` at the end of `_calendar_block` (currently):

```python
    return {
        "status": status,
        "events": events,
        "window": {
            "from": (today - dt.timedelta(days=synced_back)).isoformat(),
            "to": (today + dt.timedelta(days=synced_fwd)).isoformat(),
        },
    }
```

to:

```python
    return {
        "status": status,
        "events": events,
        "calendars": _writable_calendars(cal_google_on, google_colors),
        "window": {
            "from": (today - dt.timedelta(days=synced_back)).isoformat(),
            "to": (today + dt.timedelta(days=synced_fwd)).isoformat(),
        },
    }
```

(`cal_google_on` and `google_colors` are both already local variables in
`_calendar_block`, computed near its top — no new lookups needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -k writable_google_calendars -v`
Expected: PASS (all three)

- [ ] **Step 5: Run the full calendar test slice to confirm no regression**

Run: `pytest tests/test_api.py -k calendar -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/app.py tests/test_api.py
git commit -m "feat: list writable Google calendars in /api/calendar"
```

---

### Task 5: `POST /api/events`

**Files:**
- Modify: `src/family_hub/app.py:52` (import), and add the new route near
  `/api/calendar` (~line 2480, after the `calendar()` route)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `GoogleCalendarClient.create_event` (Task 2),
  `db.add_event_row` (Task 3), `calendar_sync.normalize_event` (existing),
  `calendar_sync.sync_once` (existing), `cfg.calendars`, `DEMO`,
  `TOKEN_PATH`, `TZ`, `_db()`, `_now_local()`.
- Produces: `POST /api/events` — request body `{calendar_id: str, title:
  str, start: str, end: str | None, all_day: bool, location: str,
  description: str}`; 200 response is the created event row (same shape
  as an `/api/calendar` events entry: `id, calendar_id, title, start_ts,
  end_ts, all_day, location, description`); 422 on validation failure, 409
  with detail `"calendar not connected"` when the token isn't configured,
  502 on a Google API failure. Consumed by the frontend (Task 8).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`, after the calendar tests. Every test that
needs a date takes `app_mod` and computes it relative to `app_mod._today()`
(matching this file's existing convention, e.g. `test_calendar_endpoint`)
rather than a hardcoded date, so the suite doesn't go stale as real time
passes:

```python
def test_add_event_rejects_unknown_calendar(client, app_mod):
    start = f"{app_mod._today().isoformat()}T09:00:00"
    r = client.post("/api/events", json={
        "calendar_id": "nope", "title": "X",
        "start": start, "all_day": False})
    assert r.status_code == 422


def test_add_event_rejects_non_google_calendar(client, app_mod):
    # An ICS-kind calendar is a read-only external feed from this app's
    # perspective, even though its id is known and well-formed. Appended
    # directly to the loaded module's cfg (the object _validate_event_calendar
    # reads) rather than round-tripping through a second config file.
    app_mod.cfg.calendars.append(
        {"id": "school", "label": "School", "kind": "ics",
         "url": "https://example.com/school.ics"})
    start = f"{app_mod._today().isoformat()}T09:00:00"
    r = client.post("/api/events", json={
        "calendar_id": "school", "title": "X",
        "start": start, "all_day": False})
    assert r.status_code == 422


def test_add_event_rejects_blank_title(client, app_mod):
    start = f"{app_mod._today().isoformat()}T09:00:00"
    r = client.post("/api/events", json={
        "calendar_id": "cal", "title": "   ",
        "start": start, "all_day": False})
    assert r.status_code == 422


def test_add_event_rejects_end_before_start(client, app_mod):
    today = app_mod._today().isoformat()
    r = client.post("/api/events", json={
        "calendar_id": "cal", "title": "X", "all_day": False,
        "start": f"{today}T09:00:00", "end": f"{today}T08:00:00"})
    assert r.status_code == 422


def test_add_event_defaults_all_day_end_to_the_next_day(client, app_mod):
    # DEMO-independent: app_mod's default config.json has no token.json, so
    # this exercises the not-connected path's validation ordering (422
    # happens before the 409 not-connected check).
    today = app_mod._today().isoformat()
    r = client.post("/api/events", json={
        "calendar_id": "cal", "title": "Trip", "all_day": True,
        "start": today})
    # validation passes (the end default is computed); it then hits the
    # not-connected 409, proving the default was computed, not rejected.
    assert r.status_code == 409


def test_add_event_not_connected_returns_409(client, app_mod):
    start = f"{app_mod._today().isoformat()}T09:00:00"
    r = client.post("/api/events", json={
        "calendar_id": "cal", "title": "Dentist", "all_day": False,
        "start": start})
    assert r.status_code == 409
    assert "not connected" in r.json()["detail"]


class _FakeWriteClient:
    """A GoogleCalendarClient stand-in used only by app.py's endpoint —
    configured() true, create_event() returns a canned item, and the
    fetch_* methods sync_once needs (called right after) return empty/ok
    so the post-write resync doesn't error."""
    created_body = None
    raise_on_create = None

    def __init__(self, token_path):
        pass

    def configured(self):
        return True

    def create_event(self, calendar_id, body):
        _FakeWriteClient.created_body = (calendar_id, body)
        if _FakeWriteClient.raise_on_create:
            raise _FakeWriteClient.raise_on_create
        return {"id": "g-new1", "summary": body["summary"],
                "start": body["start"], "end": body["end"]}

    def fetch_events(self, cal_id, lo, hi):
        return []

    def fetch_calendar_colors(self):
        return {}


def test_add_event_live_path_creates_inserts_locally_and_resyncs(client, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "GoogleCalendarClient", _FakeWriteClient)
    today = app_mod._today().isoformat()
    r = client.post("/api/events", json={
        "calendar_id": "cal", "title": "Dentist", "all_day": False,
        "start": f"{today}T09:00:00", "end": f"{today}T10:00:00",
        "location": "Clinic", "description": "bring insurance card"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Dentist" and body["id"] == "g-new1"
    # visible immediately, before any background sync tick
    ev = client.get("/api/calendar").json()["events"]
    assert any(e["id"] == "g-new1" for e in ev)
    # the Google body carried the house time zone
    cal_id, gbody = _FakeWriteClient.created_body
    assert cal_id == "cal"
    assert gbody["start"]["timeZone"] and gbody["end"]["timeZone"]


def test_add_event_live_path_google_failure_is_502_not_500(client, app_mod, monkeypatch):
    _FakeWriteClient.raise_on_create = RuntimeError("quota exceeded")
    monkeypatch.setattr(app_mod, "GoogleCalendarClient", _FakeWriteClient)
    start = f"{app_mod._today().isoformat()}T09:00:00"
    try:
        r = client.post("/api/events", json={
            "calendar_id": "cal", "title": "X", "all_day": False,
            "start": start})
    finally:
        _FakeWriteClient.raise_on_create = None
    assert r.status_code == 502


def test_add_event_demo_mode_writes_locally_with_no_client(client_demo, app_mod_demo):
    today = app_mod_demo._today().isoformat()
    tomorrow = (app_mod_demo._today() + dt.timedelta(days=1)).isoformat()
    r = client_demo.post("/api/events", json={
        "calendar_id": "cal", "title": "Birthday", "all_day": True,
        "start": today})
    assert r.status_code == 200
    assert r.json()["end_ts"] == tomorrow     # exclusive-end default
    ev = client_demo.get("/api/calendar").json()["events"]
    assert any(e["title"] == "Birthday" for e in ev)
```

These tests need a `client_demo` fixture (DEMO mode). Add it near the
existing `app_mod`/`client` fixtures in `tests/test_api.py`:

```python
@pytest.fixture
def app_mod_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "hub.db"))
    monkeypatch.setenv("DISABLE_SYNC", "1")
    monkeypatch.setenv("DEMO", "1")
    monkeypatch.setenv("CONFIG_PATH", _write_cfg(tmp_path))
    import family_hub.app as appmod
    importlib.reload(appmod)
    return appmod


@pytest.fixture
def client_demo(app_mod_demo):
    with TestClient(app_mod_demo.app) as c:
        yield c
```

`_write_cfg`'s calendars list already has an entry with `id: "cal"`
(`kind` defaults to `"google"`), so DEMO mode's add-event test above uses
`calendar_id: "cal"` to match — DEMO mode still validates against
`cfg.calendars` exactly like the live path (Task 5's `_validate_event_calendar`
doesn't branch on DEMO), it just skips the real Google call. `config.demo.json`'s
real `demo-home` calendar only applies when running the actual app with
`CONFIG_PATH=config.demo.json`, not in this test's own `_write_cfg` config.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -k add_event -v`
Expected: FAIL — `404 Not Found` on every `POST /api/events` call (the
route doesn't exist yet)

- [ ] **Step 3: Implement**

In `src/family_hub/app.py`, change the import on line 52 from:

```python
from .calendar_sync import GoogleCalendarClient, sync_once
```

to:

```python
from .calendar_sync import GoogleCalendarClient, normalize_event, sync_once
```

Then add, directly after the `calendar()` route (after line 2479's
`return _calendar_block(c, _today(), days, past_days=past)`):

```python
class EventIn(BaseModel):
    calendar_id: str
    title: str
    start: str
    end: str | None = None
    all_day: bool = False
    location: str = ""
    description: str = ""


def _validate_event_calendar(calendar_id: str) -> None:
    """Only a configured kind=='google' calendar can be written to — an
    unknown id OR a known-but-ICS one (a read-only external feed) both
    fail the same way. Defense in depth: the frontend picker already
    filters to google calendars, but a stale/tampered request must not
    reach Google with someone else's or an unwritable calendar id."""
    ok = any(c["id"] == calendar_id and c.get("kind", "google") == "google"
              for c in cfg.calendars)
    if not ok:
        raise HTTPException(422, "unknown or non-Google calendar")


def _event_start_end(body: EventIn) -> tuple[str, str]:
    """Parse/validate start (and default/validate end). All-day end
    defaults to the next day (Google's end is EXCLUSIVE); a timed event
    defaults to a 1-hour span. Raises 422 on anything unparsable or an end
    before start."""
    try:
        if body.all_day:
            start_d = dt.date.fromisoformat(body.start)
            end = body.end or (start_d + dt.timedelta(days=1)).isoformat()
            dt.date.fromisoformat(end)
        else:
            start_t = dt.datetime.fromisoformat(body.start)
            end = body.end or (start_t + dt.timedelta(hours=1)).isoformat()
            dt.datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(422, "start/end must be valid dates/datetimes")
    if end < body.start:
        raise HTTPException(422, "end must not be before start")
    return body.start, end


def _event_google_body(title: str, location: str, description: str,
                       start: str, end: str, all_day: bool) -> dict:
    body: dict = {"summary": title}
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    if all_day:
        body["start"] = {"date": start}
        body["end"] = {"date": end}
    else:
        body["start"] = {"dateTime": start, "timeZone": TZ.key}
        body["end"] = {"dateTime": end, "timeZone": TZ.key}
    return body


@app.post("/api/events")
def events_add(body: EventIn):
    title = body.title.strip()
    if not (1 <= len(title) <= 200):
        raise HTTPException(422, "title must be 1-200 characters")
    _validate_event_calendar(body.calendar_id)
    start, end = _event_start_end(body)
    c = _db()

    if DEMO:
        # No real Google account in DEMO — write straight into the local
        # cache the wall already reads, same shape as a synced row.
        row = {
            "id": f"local-{uuid.uuid4().hex[:12]}", "calendar_id": body.calendar_id,
            "title": title, "start_ts": start, "end_ts": end,
            "all_day": 1 if body.all_day else 0,
            "updated": None, "location": body.location,
            "description": body.description, "color_id": None,
        }
        fdb.add_event_row(c, row)
        return row

    client = GoogleCalendarClient(TOKEN_PATH)
    if not client.configured():
        raise HTTPException(409, "calendar not connected")
    gbody = _event_google_body(title, body.location, body.description,
                               start, end, body.all_day)
    try:
        item = client.create_event(body.calendar_id, gbody)
    except Exception as e:
        raise HTTPException(502, f"could not create the event: {e}")
    row = normalize_event(item, body.calendar_id, TZ)
    if row is None:
        # Google accepted the insert but returned a shape normalize_event
        # can't read (e.g. no start echoed back) — say so rather than
        # leaving the caller silently guessing whether it saved. It DID
        # save; the next background sync (or this one below) will still
        # pick it up from Google's own listing.
        raise HTTPException(
            502, f"event created ({item.get('id')}) but its response "
            "could not be read; it will appear once the next sync runs")
    fdb.add_event_row(c, row)
    # Doc-mandated "insert, then trigger a re-sync": reconciles colors and
    # any other drift with the same call the background thread already
    # makes every 300s.
    sync_once(client, c, cfg, _now_local())
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -k add_event -v`
Expected: PASS (all of them)

- [ ] **Step 5: Run the full Python suite, default and TZ=UTC**

Run: `pytest -q`
Run: `TZ=UTC pytest -q`
Expected: PASS both times

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/app.py tests/test_api.py
git commit -m "feat: add POST /api/events (create a calendar event)"
```

---

### Task 6: Frontend — nav button, modal shell, CSS

**Files:**
- Modify: `src/family_hub/web/static/hub.js:332-347` (`calNavHtml`)
- Modify: `src/family_hub/web/static/index.html` (near the `chore-modal`
  block, ~line 192)
- Modify: `src/family_hub/web/static/styles.css` (after the `.chore-close`
  block, ~line 1903)
- Test: `tests/js/hub-dom.test.mjs`

**Interfaces:**
- Produces: a `data-caladd="1"` button inside `calNavHtml`'s output; DOM
  ids `add-event-modal` / `add-event-card` / `add-event-form`; CSS classes
  `.add-event-modal` / `.add-event-card` / `.add-event-close`. Consumed by
  Task 8's `openAddEventModal`/`closeAddEventModal` and by the JS test
  harness's `SEEDED_IDS`.

- [ ] **Step 1: Write the failing test**

Add to `tests/js/hub-dom.test.mjs`, near the other `calNavHtml`-adjacent
tests (after the `renderCalFull` tests, e.g. after line ~1233):

```js
test('calNavHtml includes an add-event button', () => {
  const { sandbox } = newHub();
  const html = sandbox.calNavHtml('October 2026');
  assert.match(html, /data-caladd="1"/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/hub-dom.test.mjs` (or via `pytest
tests/test_js.py -v` if Node isn't on PATH but Docker is)
Expected: FAIL — `data-caladd` not found in `calNavHtml`'s output

- [ ] **Step 3: Implement**

In `src/family_hub/web/static/hub.js`, change `calNavHtml` (currently):

```js
  return `<div class="cal-nav">`
    + `<button class="cal-nav-btn" type="button" data-calnav="prev">‹</button>`
    + `<button class="cal-nav-btn cal-nav-today" type="button" data-calnav="today">Today</button>`
    + `<button class="cal-nav-btn" type="button" data-calnav="next">›</button>`
    + `<span class="cal-nav-title">${escapeHtml(title)}</span>`
    + `<span class="spacer"></span>`
    + `<div class="segmented">${seg('month', 'Month')}${seg('agenda', 'Week')}</div>`
    + `</div>`;
```

to:

```js
  return `<div class="cal-nav">`
    + `<button class="cal-nav-btn" type="button" data-calnav="prev">‹</button>`
    + `<button class="cal-nav-btn cal-nav-today" type="button" data-calnav="today">Today</button>`
    + `<button class="cal-nav-btn" type="button" data-calnav="next">›</button>`
    + `<span class="cal-nav-title">${escapeHtml(title)}</span>`
    + `<span class="spacer"></span>`
    + `<div class="segmented">${seg('month', 'Month')}${seg('agenda', 'Week')}</div>`
    + `<button class="cal-nav-btn cal-nav-add" type="button" data-caladd="1" aria-label="Add event">+</button>`
    + `</div>`;
```

In `src/family_hub/web/static/index.html`, add directly after the
`chore-modal` block (after its closing `</div>` at line 192):

```html
  <!-- Add-event modal: opened by the "+" button in the calendar overlay's
       nav row (calNavHtml). Structurally identical to chore-modal (a
       reusable form host + close button), its own class names so the
       delegated click handler's .chore-close backdrop check can't also
       catch taps meant for this modal. -->
  <div class="add-event-modal hidden" id="add-event-modal" role="dialog" aria-modal="true" aria-label="Add event" tabindex="-1">
    <div class="add-event-card" id="add-event-card">
      <button class="add-event-close" type="button" aria-label="Close">✕</button>
      <div id="add-event-form"></div>
    </div>
  </div>
```

In `src/family_hub/web/static/styles.css`, add directly after the
`.chore-close:focus-visible` rule (after line 1902):

```css
/* ============ add-event modal (calendar overlay's "+" button) ============ */
/* Same layering/sizing as .chore-modal/.chore-card (a reusable form host),
   under its own class names — sharing .chore-modal's classes would make the
   delegated click handler's backdrop-tap check for .chore-modal ALSO catch
   this modal and call the wrong close function. */
.add-event-modal {
  position: fixed; inset: 0; z-index: 90;
  background: rgba(0, 0, 0, 0.62);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 24px; overflow-y: auto;
}
.add-event-card {
  position: relative;
  width: 100%; max-width: 560px; margin: auto;
  background: var(--surface);
  border: 1px solid var(--edge);
  border-radius: 16px;
  padding: 52px 26px 26px 26px;
}
#add-event-form { display: flex; flex-direction: column; gap: 18px; }
.add-event-close {
  position: absolute; top: 14px; right: 14px;
  width: 40px; height: 40px;
  font-size: 16px; color: var(--dim);
  background: var(--surface-2);
  border: 1px solid var(--edge);
  border-radius: 50%; cursor: pointer;
}
.add-event-close:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/hub-dom.test.mjs` (filter to the new test, or
run the whole file — it's fast)
Expected: PASS

- [ ] **Step 5: Add the new ids to the JS test harness's SEEDED_IDS**

In `tests/js/hub-dom.test.mjs`, add `'add-event-modal', 'add-event-card',
'add-event-form'` to the `SEEDED_IDS` array (~line 35-43), next to
`'chore-modal', 'chore-card', 'chore-editor'` — all three are needed:
`openAddEventModal`/`closeAddEventModal` (Task 8) look up
`add-event-modal` and `add-event-card` directly, and `buildAddEventForm`
(Task 7) is handed the `add-event-form` host to build into.

- [ ] **Step 6: Run the full JS suite to confirm no regression**

Run: `pytest tests/test_js.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/family_hub/web/static/hub.js src/family_hub/web/static/index.html \
        src/family_hub/web/static/styles.css tests/js/hub-dom.test.mjs
git commit -m "feat: add the add-event modal shell and nav button"
```

---

### Task 7: Frontend — the reusable form (`buildAddEventForm`)

**Files:**
- Modify: `src/family_hub/web/static/common.js` (after `freshPersonModel`,
  ~line 1021)
- Test: `tests/js/hub.test.mjs` (pure-helper tests — no DOM needed for
  `buildEventPayload`; `hub-dom.test.mjs` covers the DOM-building half in
  Task 8, once `openAddEventModal` calls it for real)

**Interfaces:**
- Consumes: `escapeHtml`, `todayISO`, `addDays` (all existing in
  common.js).
- Produces: `freshEventModel() -> object` (`{title, calendarId, date,
  allDay, startTime, endTime, location, description}`);
  `buildEventPayload(model) -> object` (the exact `POST /api/events`
  body shape: `{calendar_id, title, start, end, all_day, location,
  description}`); `buildAddEventForm(host, calendars, submitLabel,
  onsubmit)` — `calendars` is the `[{id, label, color}]` list from Task 4;
  after the form's own client-side checks pass (non-blank title, end time
  not before start time), `onsubmit(body, errEl)` is called with the
  built payload and the form's own `.f-error` node (so a server-side
  failure can render in the same place a client-side one would). Consumed
  by Task 8's `openAddEventModal`, whose `submitAddEvent(body, errEl)` is
  the real `onsubmit`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/js/hub.test.mjs` (the pure-helper suite — check its existing
import style at the top of the file and match it; it loads `common.js`
the same way `hub-dom.test.mjs` loads `hub.js`, into a `vm` sandbox, so
`buildEventPayload` and `freshEventModel` surface as sandbox globals):

```js
test('freshEventModel defaults to today, timed, 09:00-10:00, no calendar chosen', () => {
  const { sandbox } = newCommon();   // match this file's existing sandbox helper name
  const m = sandbox.freshEventModel();
  assert.equal(m.allDay, false);
  assert.equal(m.calendarId, '');
  assert.equal(m.startTime, '09:00');
  assert.equal(m.endTime, '10:00');
});

test('buildEventPayload: a timed event combines date+time into start/end', () => {
  const { sandbox } = newCommon();
  const body = sandbox.buildEventPayload({
    title: '  Dentist  ', calendarId: 'cal', date: '2026-10-01',
    allDay: false, startTime: '09:00', endTime: '10:00',
    location: '  Clinic  ', description: '',
  });
  assert.deepEqual(body, {
    calendar_id: 'cal', title: 'Dentist', start: '2026-10-01T09:00:00',
    end: '2026-10-01T10:00:00', all_day: false, location: 'Clinic',
    description: '',
  });
});

test('buildEventPayload: an all-day event sends the NEXT day as the exclusive end', () => {
  const { sandbox } = newCommon();
  const body = sandbox.buildEventPayload({
    title: 'Trip', calendarId: 'cal', date: '2026-10-01', allDay: true,
    startTime: '09:00', endTime: '10:00', location: '', description: '',
  });
  assert.equal(body.start, '2026-10-01');
  assert.equal(body.end, '2026-10-02');
  assert.equal(body.all_day, true);
});
```

(If `tests/js/hub.test.mjs` uses a different sandbox-helper name than
`newCommon`, use whatever that file already calls it — check its top for
the existing pattern before writing these; do not invent a second one.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/hub.test.mjs`
Expected: FAIL — `freshEventModel is not defined` / `buildEventPayload is
not defined`

- [ ] **Step 3: Implement**

In `src/family_hub/web/static/common.js`, add after `freshPersonModel`
(~line 1021):

```js
function freshEventModel() {
  return { title: '', calendarId: '', date: todayISO(), allDay: false,
           startTime: '09:00', endTime: '10:00', location: '', description: '' };
}

/* The POST /api/events body. All-day end is the day AFTER the picked date
   (Google's exclusive-end convention — _event_start_end on the server
   applies the same default when `end` is omitted, but the client always
   sends it explicitly so the picker's summary and the saved event agree). */
function buildEventPayload(f) {
  const date = f.date || todayISO();
  const allDay = !!f.allDay;
  return {
    calendar_id: f.calendarId,
    title: (f.title || '').trim(),
    start: allDay ? date : `${date}T${f.startTime || '09:00'}:00`,
    end: allDay ? addDays(date, 1) : `${date}T${f.endTime || f.startTime || '10:00'}:00`,
    all_day: allDay,
    location: (f.location || '').trim(),
    description: (f.description || '').trim(),
  };
}

/* The add-event form (mirrors buildChoreForm's shape: innerHTML the whole
   thing, then wire handlers via querySelector). `calendars` is the
   [{id,label,color}] list from /api/calendar (Task 4) — empty means no
   writable calendar is configured, and the form says so instead of
   showing a picker with nothing in it. */
function buildAddEventForm(host, calendars, submitLabel, onsubmit) {
  const model = freshEventModel();
  if (calendars.length) model.calendarId = calendars[0].id;
  if (!calendars.length) {
    host.innerHTML = `<div class="hint">No calendar is set up to add events to yet.</div>`;
    return;
  }
  host.innerHTML = `
    <div class="field"><label>Title</label>
      <input class="txt-input f-title" maxlength="200" autocomplete="off"></div>
    <div class="field"><label>Calendar</label>
      <select class="txt-input f-calendar">${calendars.map((cal) =>
        `<option value="${escapeHtml(cal.id)}">${escapeHtml(cal.label)}</option>`).join('')}</select></div>
    <div class="field"><label>Date</label>
      <input class="txt-input f-evdate" type="date"></div>
    <div class="field">
      <label><input class="f-allday" type="checkbox"> All day</label></div>
    <div class="field f-timerow"><label>Time</label>
      <div class="interval-row">
        <input class="txt-input f-starttime" type="time">
        <span class="interval-word">to</span>
        <input class="txt-input f-endtime" type="time">
      </div></div>
    <div class="field"><label>Location (optional)</label>
      <input class="txt-input f-location" maxlength="200" autocomplete="off"></div>
    <div class="field"><label>Description (optional)</label>
      <input class="txt-input f-description" maxlength="2000" autocomplete="off"></div>
    <div class="form-error hidden f-error"></div>
    <button class="btn-primary" type="button" data-submit>${escapeHtml(submitLabel)}</button>`;

  const $ = (sel) => host.querySelector(sel);
  $('.f-evdate').value = model.date;
  $('.f-starttime').value = model.startTime;
  $('.f-endtime').value = model.endTime;

  const paintAllDay = () => {
    $('.f-timerow').classList.toggle('hidden', model.allDay);
  };
  paintAllDay();
  $('.f-allday').onchange = (e) => { model.allDay = e.target.checked; paintAllDay(); };

  $('[data-submit]').onclick = oneSaveAtATime($('[data-submit]'), () => {
    const err = $('.f-error');
    err.classList.add('hidden');
    const title = $('.f-title').value.trim();
    if (!title) {
      err.textContent = 'Enter a title.';
      err.classList.remove('hidden');
      return undefined;
    }
    model.title = title;
    model.calendarId = $('.f-calendar').value;
    model.date = $('.f-evdate').value || todayISO();
    model.location = $('.f-location').value;
    model.description = $('.f-description').value;
    model.startTime = $('.f-starttime').value || model.startTime;
    model.endTime = $('.f-endtime').value || model.endTime;
    if (!model.allDay && model.endTime < model.startTime) {
      err.textContent = 'End time must not be before start time.';
      err.classList.remove('hidden');
      return undefined;
    }
    return onsubmit(buildEventPayload(model), err);
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/hub.test.mjs`
Expected: PASS

- [ ] **Step 5: Run the full JS suite to confirm no regression**

Run: `pytest tests/test_js.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/web/static/common.js tests/js/hub.test.mjs
git commit -m "feat: add the reusable add-event form (buildAddEventForm)"
```

---

### Task 8: Frontend — wiring (open/close/submit, MODAL_CLOSERS, Escape, click delegation)

**Files:**
- Modify: `src/family_hub/web/static/hub.js`:
  - `MODAL_CLOSERS` (~line 1850)
  - the delegated click handler (~line 4029-4062)
  - the Escape-key handler (~line 5102-5115)
  - add `openAddEventModal`, `closeAddEventModal`, `submitAddEvent`
    (near `openEventDetail`/`closeEventDetail`, ~line 448)
- Test: `tests/js/hub-dom.test.mjs`

**Interfaces:**
- Consumes: `buildAddEventForm` (Task 7), `calWin.calendars` (Task 4, via
  `/api/calendar`), `dialogOpened`/`dialogClosed`/`armIdle` (existing),
  `attemptTodo`-style fetch via `j()` (existing), `renderCalFull`
  (existing — repaints the calendar after a successful add).
- Produces: `openAddEventModal()`, `closeAddEventModal()` — public
  entry points wired to `data-caladd` and the modal's close/backdrop.

- [ ] **Step 1: Write the failing tests**

Add to `tests/js/hub-dom.test.mjs`, after the `openEventDetail`/
`closeEventDetail` tests (search for `openEventDetail` to find that
neighborhood; the existing tests around line 420-454's functions don't
have their own `.test.mjs` block yet in this file — add a new block near
the other modal tests, e.g. after the `chore-modal`-adjacent tests):

```js
test('openAddEventModal populates the calendar picker from calWin.calendars', () => {
  const { document, sandbox } = newHub();
  vm.runInContext(
    "calWin = { calendars: [{id: 'cal', label: 'Fam', color: '#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };",
    sandbox);

  sandbox.openAddEventModal();

  const modal = document.getElementById('add-event-modal');
  assert.equal(modal.classList.contains('hidden'), false);
  const formHtml = document.getElementById('add-event-form').innerHTML;
  assert.match(formHtml, /value="cal"/);
  assert.match(formHtml, />Fam</);
});

test('openAddEventModal shows a message instead of a picker when no calendar is configured', () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);

  sandbox.openAddEventModal();

  const form = document.getElementById('add-event-form');
  assert.match(form.innerHTML, /No calendar is set up/);
});

test('closeAddEventModal hides the modal and clears the form host', () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [{id:'cal',label:'Fam',color:'#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);
  sandbox.openAddEventModal();

  sandbox.closeAddEventModal();

  assert.equal(document.getElementById('add-event-modal').classList.contains('hidden'), true);
  assert.equal(document.getElementById('add-event-form').innerHTML, '');
});

test('MODAL_CLOSERS closes the add-event modal too (surfaceOpen/wallBusy/idle-return coverage)', () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [{id:'cal',label:'Fam',color:'#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);
  sandbox.openAddEventModal();

  assert.equal(sandbox.surfaceOpen(), true, 'an open add-event modal counts as a busy surface');
  // MODAL_CLOSERS is a top-level `const` — not proxied onto the sandbox
  // object, so it's invoked by running an expression IN the context.
  vm.runInContext("MODAL_CLOSERS['add-event-modal']()", sandbox);
  assert.equal(document.getElementById('add-event-modal').classList.contains('hidden'), true);
});

test('buildAddEventForm: a fast double-tap on submit only calls onsubmit once (oneSaveAtATime wiring)', () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [{id:'cal',label:'Fam',color:'#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);
  let calls = 0;
  // A never-resolving promise: the button stays disabled the whole test,
  // proving the SECOND click is a no-op rather than a second submit.
  sandbox.openAddEventModal();
  const host = document.getElementById('add-event-form');
  sandbox.buildAddEventForm(host, [{ id: 'cal', label: 'Fam', color: '#5BC9F0' }],
    'Add event', () => { calls += 1; return new Promise(() => {}); });
  host.querySelector('.f-title').value = 'Dentist';
  const btn = host.querySelector('[data-submit]');
  btn.onclick();
  btn.onclick();
  assert.equal(calls, 1, 'the second tap while the first save is in flight must be a no-op');
});

test('submitAddEvent success closes the modal, shows the new event, and escapes a hostile title', async () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [{id:'cal',label:'Fam',color:'#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);
  const created = { id: 'g1', calendar_id: 'cal', title: '<img src=x onerror=alert(1)>',
    start_ts: '2026-10-01T09:00:00', end_ts: '2026-10-01T10:00:00', all_day: 0,
    location: '', description: '' };
  sandbox.j = async () => created;
  sandbox.poll = async () => {};   // avoid a real /api/hub round trip in this test
  sandbox.openAddEventModal();

  const err = document.createElement('div');
  await sandbox.submitAddEvent(
    { calendar_id: 'cal', title: created.title, start: created.start_ts,
      end: created.end_ts, all_day: false, location: '', description: '' },
    err);

  assert.equal(document.getElementById('add-event-modal').classList.contains('hidden'), true);
  // evIndex is a top-level `const` in hub.js — not proxied onto the sandbox
  // object, so it's read back by running an expression IN the context
  // (same pattern as the existing pruneEvIndex test), not sandbox.evIndex.
  assert.ok(vm.runInContext("!!evIndex['g1']", sandbox),
    'the new event is indexed for the calendar render');
  // the render path (monthWeekHtml/agendaHtml) escapes on output already —
  // this pins that the RAW title (unescaped) is what's stored, so a render
  // bug that stopped escaping would be caught by the existing XSS test
  // (hub-dom.test.mjs: "safeColor is applied at the color sinks..."), while
  // this test pins that submitAddEvent doesn't pre-escape (which would
  // double-escape on render).
  assert.equal(vm.runInContext("evIndex['g1'].title", sandbox), created.title);
});

test('submitAddEvent keeps the modal open and shows an inline error on failure', async () => {
  const { document, sandbox } = newHub();
  vm.runInContext("calWin = { calendars: [{id:'cal',label:'Fam',color:'#5BC9F0'}], events: [], window: {from:'2026-01-01', to:'2026-12-31'} };", sandbox);
  sandbox.j = async () => { throw new Error('calendar not connected'); };
  sandbox.openAddEventModal();   // builds the real form, including its .f-error node

  // The exact date is irrelevant here (submitAddEvent doesn't validate it —
  // that's the server's job, already covered in Task 5); j() is mocked to
  // reject regardless of payload, so any well-formed string will do.
  const errEl = document.getElementById('add-event-form').querySelector('.f-error');
  await sandbox.submitAddEvent(
    { calendar_id: 'cal', title: 'X', start: '2026-10-01T09:00:00', all_day: false },
    errEl);

  assert.equal(document.getElementById('add-event-modal').classList.contains('hidden'), false,
    'a failed write must not close the modal — the typed data stays');
  assert.match(errEl.textContent, /connected/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/hub-dom.test.mjs`
Expected: FAIL — `openAddEventModal is not a function` etc.

- [ ] **Step 3: Implement**

In `src/family_hub/web/static/hub.js`, add near `openEventDetail`/
`closeEventDetail` (after `closeEventDetail`, ~line 453):

```js
/* --------------------------------------------------------- add event */

function openAddEventModal() {
  const calendars = (calWin && calWin.calendars) || [];
  const host = document.getElementById('add-event-form');
  buildAddEventForm(host, calendars, 'Add event', submitAddEvent);
  document.getElementById('add-event-modal').classList.remove('hidden');
  dialogOpened('add-event-modal',
    document.getElementById('add-event-card').querySelector('.add-event-close'));
  armIdle();
}

function closeAddEventModal() {
  document.getElementById('add-event-modal').classList.add('hidden');
  dialogClosed('add-event-modal');
  document.getElementById('add-event-form').innerHTML = '';
}

/* buildAddEventForm's submit handler: POST, then on success close + repaint
   the calendar from the response (no need to wait for the next poll); on
   failure leave the modal open (the typed data is still in the form) and
   show the message inline, mirroring the doc's "never lose what they
   typed" requirement. `errEl` is the form's own .f-error node. */
async function submitAddEvent(body, errEl) {
  let created;
  try {
    created = await j('/api/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    const msg = (e.message || '').includes('not connected')
      ? "Calendar isn't connected — check Settings."
      : (e.message || "Couldn't save — check the hub and try again.");
    errEl.textContent = msg;
    errEl.classList.remove('hidden');
    return;
  }
  closeAddEventModal();
  indexEvents([...(calWin && calWin.events || []), created]);
  if (calWin) calWin.events = [...(calWin.events || []), created];
  if (openView === 'calendar') renderCalFull();
  await poll();   // refresh the home-card agenda too
}
```

Change `MODAL_CLOSERS` (currently, ~line 1850):

```js
const MODAL_CLOSERS = {
  'ev-modal': () => closeEventDetail(),
  'chore-modal': () => closeChoreEditor(),
  'confirm-modal': () => closeDeleteConfirm(),
};
```

to:

```js
const MODAL_CLOSERS = {
  'ev-modal': () => closeEventDetail(),
  'chore-modal': () => closeChoreEditor(),
  'confirm-modal': () => closeDeleteConfirm(),
  'add-event-modal': () => closeAddEventModal(),
};
```

In the delegated click handler (~line 4029), add the add-event open/close
wiring. Directly after the existing chore-editor close check (before the
`ev-close` check, ~line 4044):

```js
  // add-event modal: ✕ or a backdrop tap dismisses it
  if (e.target.closest('.add-event-close')
      || (e.target.closest('.add-event-modal') && !e.target.closest('.add-event-card'))) {
    closeAddEventModal(); return;
  }
```

And add the OPEN trigger next to the other `data-cal*` checks (after the
`data-calback` check, ~line 4057):

```js
  if (e.target.closest('[data-caladd]')) { openAddEventModal(); return; }
```

In the Escape-key handler (~line 5102), add a check at the same tier as
`chore-modal` (directly after it, before `ev-modal`):

```js
  if (modalShown('chore-modal')) { closeChoreEditor(); return; }
  if (modalShown('add-event-modal')) { closeAddEventModal(); return; }
  if (modalShown('ev-modal')) { closeEventDetail(); return; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/hub-dom.test.mjs`
Expected: PASS

- [ ] **Step 5: Run the full JS suite to confirm no regression**

Run: `pytest tests/test_js.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/family_hub/web/static/hub.js tests/js/hub-dom.test.mjs
git commit -m "feat: wire the add-event modal (open/close/submit, Escape, MODAL_CLOSERS)"
```

---

### Task 9: Static guard, changelog, README, docs/hub.png

**Files:**
- Modify: `tests/test_static.py`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `docs/hub.png` (regenerated, not hand-edited)

**Interfaces:**
- Consumes: nothing new — this task only adds a regression guard and
  docs for everything Tasks 1-8 built.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_static.py`, near `test_off_features_hide_their_wall_surface`:

```python
def test_add_event_modal_is_wired_through_the_shared_modal_machinery():
    """The add-event modal must participate in the same close/idle/wallBusy
    machinery every other modal does (CLAUDE.md: 'a new modal or popover
    goes in the set surfaceOpen() and wallBusy() read, closes on idle and
    on Escape') — not a bespoke, easy-to-forget parallel path."""
    hub = (STATIC / "hub.js").read_text()
    assert re.search(r"'add-event-modal':\s*\(\)\s*=>\s*closeAddEventModal\(\)", hub), \
        "add-event-modal must be registered in MODAL_CLOSERS"
    assert re.search(r"modalShown\('add-event-modal'\)", hub), \
        "add-event-modal must be checked in the Escape-key handler"
    index = (STATIC / "index.html").read_text()
    assert 'id="add-event-modal"' in index and 'id="add-event-card"' in index
```

- [ ] **Step 2: Run test to verify it fails**

(This should already PASS after Task 8 — this step confirms the guard
correctly detects the wiring, by temporarily checking it against the
pre-Task-8 state is not practical this late in the plan. Instead: run it
now and confirm it PASSES, proving Task 8's wiring is real, then treat
this as the regression guard going forward.)

Run: `pytest tests/test_static.py -k add_event_modal_is_wired -v`
Expected: PASS (Task 8 already did the work; this pins it)

- [ ] **Step 3: Add the CHANGELOG entry**

In `CHANGELOG.md`, add a new `### Added` subsection under the existing
`## [Unreleased]` heading (above the current `### Fixed` entry):

Insert the new `### Added` subsection directly below the `## [Unreleased]`
line, ABOVE the existing `### Fixed` heading — do not alter the existing
`### Fixed` entry's text at all, only insert before it:

```markdown
## [Unreleased]

### Added
- The calendar overlay has a "+" button to add an event directly to any
  configured Google calendar, with immediate visibility and no wait for
  the next background sync.

### Fixed
- The Wyze bridge's health check now also probes the bridge's own internal
  go2rtc. That relay can exit alone right after the container starts, and
  the bridge never relaunches it, so the Wyze cameras went dark while the
  container still reported healthy. After three failed tries the check now
  restarts the bridge, which brings the relay back.
```

- [ ] **Step 4: Add the README bullet**

In `README.md`, find the "What it looks like" bullet list (the same list
the gauntlet doc's item 8 references) and add one bullet describing
add-event, matching the existing bullets' voice/length.

- [ ] **Step 5: Regenerate docs/hub.png**

Run the demo server and screenshot it at 1920px wide, full page, per
CLAUDE.md's documented procedure:

```bash
DEMO=1 DISABLE_SYNC=1 CONFIG_PATH=config.demo.json PORT=8199 python -m family_hub.app &
```

Then screenshot `http://localhost:8199/` at exactly 1920px width, full
page height, and save over `docs/hub.png`. Stop the demo server
afterward. (This step needs a real browser — use whatever screenshot
tooling is available in the execution environment; if none is available,
flag this step to the operator rather than skipping the file silently.)

- [ ] **Step 6: Run the full Python suite (changelog-guard included)**

Run: `pytest -q`
Expected: PASS, including `tests/test_check_changelog.py`

- [ ] **Step 7: Commit**

```bash
git add tests/test_static.py CHANGELOG.md README.md docs/hub.png
git commit -m "docs: changelog, README bullet, and hub.png for add-event"
```

---

### Task 10: Full verification and review gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python suite, both environments**

Run: `pytest -q`
Run: `TZ=UTC pytest -q`
Expected: PASS both times, with the true count of collected tests shown
(not a silent 0-collected pass)

- [ ] **Step 2: Run the full JS suite**

Run: `pytest tests/test_js.py -v`
Expected: PASS, `# fail 0` in the output, and NOT `# tests 0`

- [ ] **Step 3: Confirm the pre-commit changelog/privacy hooks are installed**

Run: `bash scripts/install-hooks.sh`
Expected: hook installed (idempotent if already present)

- [ ] **Step 4: Run the three pr-review-toolkit agents on the branch diff**

Dispatch `pr-review-toolkit:silent-failure-hunter`,
`pr-review-toolkit:code-reviewer`, and `pr-review-toolkit:pr-test-analyzer`
against the full diff introduced by Tasks 1-9 (`git diff main...HEAD` or
equivalent). Fix every real finding (or explicitly reject one with
reasoning recorded in the commit message); for any genuine bug found, add
the guard/test that would have caught it, per CLAUDE.md's meta-rule.

- [ ] **Step 5: Re-run affected tests after any review fixes**

Run: `pytest -q && pytest tests/test_js.py -v`
Expected: PASS

- [ ] **Step 6: If the branch grew substantially fixing review findings, re-run the three agents**

Per CLAUDE.md: "Re-review when the branch has grown substantially since
the last pass."

- [ ] **Step 7: Hand off to the operator for what this session cannot verify**

Report to the operator that the following CLAUDE.md-required checks still
need them directly (this session has no real iPhone, no physical wall
panel, and no Firefox ESR):
- Real iPhone check on the add-event modal and the "+" button.
- Physical wall panel visual check (gamma/contrast).
- Firefox ESR rendering check.
- Re-running `scripts/google-auth.py` with the new scope and deploying
  the refreshed `token.json` (this was explicitly out of scope for this
  session — see the design spec's "Not done by this feature" section).
