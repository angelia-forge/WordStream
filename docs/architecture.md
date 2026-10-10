# WordStream Architecture

## Scope

WordStream is a single-user, mobile-first words and fixed phrases read-along
PWA. The MVP uses a modular FastAPI monolith, server-rendered pages, SQLite,
and browser TTS. It does not claim offline learning: the service worker only
caches the app shell and static assets.

## Layers

- `api`: HTTP validation, authentication, status codes, and response schemas.
- `web`: Jinja2 pages, HTMX fragments, and Alpine.js player state.
- `services`: use cases and transaction boundaries.
- `repositories`: persistence operations without transaction ownership.
- `models`: SQLAlchemy persistence models.
- `schemas`: Pydantic request and response models.

Each use case owns one Unit of Work. Repositories may query, add, and flush,
but must not commit or roll back. A service either commits the complete use
case or rolls it back.

## Learning contract

The MVP uses binary Leitner outcomes rather than four-level SM-2 ratings.

- Automatic advance settles the current entry as `seen`.
- Selecting `again` requeues the same session item at the end of the current
  queue. It does not create a new `SessionItem`.
- Every display of that item increments its server-side `attempt_count`.
- An item may have many attempts, but produces exactly one final
  `LearningEvent`.
- `seen` advances the entry through intervals of 1, 3, 7, 14, and 30 days.
- `again` returns the entry to box 0 and makes it due the following day.
- TTS is progressive enhancement. Failure disables speech without stopping
  timing, navigation, or outcome recording.

The client buffers settled outcomes and flushes after ten items, on pause, on
page visibility loss, and when the session finishes. Pending batches may be
kept in local storage until acknowledged. This is retry protection, not
offline learning support.

## Event authority

- The server generates `session_item_id` values when a study session is
  created. Clients only reference them.
- Every presentation generates a client UUID `attempt_id`. Pending attempts
  are persisted with the pending outcome and submitted in the same atomic
  batch.
- The server deduplicates attempt ids per session item and derives
  `attempt_count` from accepted attempts. A client aggregate count may be
  retained for audit, but never drives scheduling.
- A client `occurred_at` is accepted only when it is within 24 hours before or
  after the server UTC time. Otherwise the request fails with
  `VALIDATION_ERROR`.
- The server stores both accepted client time and server receipt time.
- Each event stores the IANA timezone active when it is written and its derived
  local activity date. Later timezone changes do not rewrite history.

## History and deletion

`LearningEvent` is append-only. Deleting a vocabulary removes its entries, plan,
active review state, and unfinished session data, but preserves learning
events. Event foreign keys use `SET NULL` and retain compact snapshots:

- immutable term key and term snapshot;
- vocabulary id and name only;
- no entry list or full vocabulary payload.

Statistics therefore remain stable after vocabulary deletion.

## Data evolution

Alembic is required from the initial schema. The application never uses
`create_all` in normal startup. CI verifies a clean upgrade to `head` and an
upgrade from the previous revision when one exists. SQLite downgrade support
is not promised because many schema changes require table recreation; local
rollback uses database backup/restore or drop-and-upgrade.

## Security boundary

The data model remains single-user. Local development may explicitly disable
authentication. Public deployments require a configured password hash,
session signing key, HTTPS, same-origin requests, and CSRF validation for
cookie-authenticated writes. API automation may use a configured API key.
Production startup fails when the security gate is not configured.

## Observability

Request middleware accepts a valid `X-Request-ID` or generates a UUIDv4. The
same value is returned in the response header, attached to structured standard
library logs, and included in structured errors. Secrets and imported content
must not be logged.
