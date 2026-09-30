# Privacy Policy — family-hub (self-hosted)

family-hub is self-hosted software. This deployment is operated by a single
household for its own private use — there is no multi-tenant service, no
account signup, and no data shared with any third party or with the
software's authors.

## What this instance accesses

When Google Calendar integration is enabled, this instance uses a Google
OAuth token — authorized directly by the operator, for the operator's own
Google account — to read and create events on the operator's own calendars.
That data:

- Is stored only on the operator's own server, in a local SQLite database.
- Is never transmitted to any third party, any analytics service, or the
  authors of this software.
- Is used only to display the operator's own calendar on their own
  household's display hardware.

## Revoking access

The operator can revoke this application's access at any time via
[Google Account → Security → Third-party apps with account access](https://myaccount.google.com/permissions).
Revoking access stops calendar sync; no other data is affected.

## Contact

This is unlisted, personal software with no public support channel. Issues
are tracked on the project's GitHub repository.
