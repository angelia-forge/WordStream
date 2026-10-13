# WordStream API Contract

All application APIs use `/api/v1`. Errors have this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [],
    "request_id": "8ed0ad8a-9e0e-4fb6-a65e-53ffecb8e64d"
  }
}
```

## `GET /api/v1/health`

Public health check. It reports application, database, and migration status
without exposing database paths or credentials.

## `POST /api/v1/auth/login`

Accepts the shared application password and creates a signed, HTTP-only
session cookie. The response includes the CSRF token required by subsequent
cookie-authenticated write requests.

## `POST /api/v1/auth/logout`

Clears the session. Requires a valid CSRF token when cookie authentication is
enabled.

## `GET /api/v1/settings`

Returns the singleton application preferences.

## `PATCH /api/v1/settings`

Updates one or more preferences. The singleton uses primary key `id = 1` and a
database check constraint prevents other ids. Preferences are `timezone`,
`tts_rate`, `default_interval`, and `daily_goal`.

## `GET /api/v1/vocabularies`

Lists vocabularies with `page`, `page_size`, `q`, `sort`, and `order`
parameters. Sorting supports `created_at`, `name`, and `entry_count`.

## `GET /api/v1/vocabularies/{id}/words`

Lists entries with pagination, term or meaning search, exact case-insensitive
tag filtering, and sorting by term, creation time, part of speech, or type.

## `DELETE /api/v1/vocabularies/{id}`

Requires `confirm_id={id}`. A missing or mismatched confirmation returns
`CONFIRMATION_REQUIRED`. Deletion cascades to entries and active study state;
learning events remain and their `entry_id` becomes null.

## `GET /api/v1/vocabularies/{id}/plan`

Returns the vocabulary's study plan. An existing vocabulary without a plan
returns `404 PLAN_NOT_FOUND`.

## `PUT /api/v1/vocabularies/{id}/plan`

Creates or updates the vocabulary's single plan and always returns `200`.
The request contains `daily_new_count`, `daily_review_count`,
`interval_seconds`, `is_random`, and `is_loop`. Daily counts accept zero
through 500; the interval accepts one through ten seconds.

Queue generation selects due review states with `next_review_at <= now` and
entries without any review state. Review entries always precede new entries.
Random mode shuffles each group independently, while loop mode is returned as
player metadata and does not change server ordering.

## `GET /api/v1/statistics`

Returns `total_events`, `learned_days`, and `streak`. These values are computed
from retained learning-event snapshots and do not change when a vocabulary is
deleted.

## Error codes

The common codes include `VALIDATION_ERROR`, `UNAUTHORIZED`, `CSRF_FAILED`,
`RATE_LIMITED`, `AUTH_DISABLED`, `RESOURCE_NOT_FOUND`, and
`CONFIRMATION_REQUIRED`. Study plan lookup also defines `PLAN_NOT_FOUND`.
