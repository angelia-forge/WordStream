# API Contract

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

## Stage 0 endpoints

### `GET /health`

Public health check. It reports application, database, and migration status
without exposing database paths or credentials.

### `POST /api/v1/auth/login`

Accepts a shared password and creates a signed, HTTP-only session cookie. The
response includes the CSRF token required by subsequent cookie-authenticated
write requests.

### `POST /api/v1/auth/logout`

Clears the session. Requires a valid CSRF token when cookie authentication is
enabled.

### `GET /api/v1/settings`

Returns the singleton application preferences.

### `PATCH /api/v1/settings`

Updates one or more preferences. The singleton uses primary key `id = 1` and a
database check constraint prevents other ids. Preferences are `timezone`,
`tts_rate`, `default_interval_seconds`, and `daily_goal`.

## Planned vocabulary endpoints

- Each imported item becomes an `Entry` with `entry_type=word|phrase`, `term`,
  and normalized term. Internal whitespace in `term` is preserved.
- Import uses `multipart/form-data` with `file`, `name`, and
  `duplicate_policy=skip`.
- List endpoints use `page >= 1`, `1 <= page_size <= 100`, `q`, an enumerated
  `sort`, and `order=asc|desc`.
- Deletion uses
  `DELETE /api/v1/vocabularies/{id}?confirm_id={id}`. A missing or mismatched
  confirmation returns `409 CONFIRMATION_REQUIRED`.
- A study plan has `UNIQUE(vocabulary_id)` and is upserted with `PUT`.

## Planned study endpoints

`POST /api/v1/study-sessions` creates the queue and server-generated
`session_item_id` values. The request contains `vocabulary_id` and
`resume_existing`; the response snapshots the active plan.

Settled outcomes use:

```text
POST /api/v1/study-sessions/{session_id}/outcomes/batch
```

Each outcome contains `session_item_id`, `client_event_id`, `result`,
`attempts`, optional `client_attempt_count`, and `occurred_at`. Every attempt
contains a client-generated UUID `attempt_id` and its client timestamp.

- A retry reuses the same `SessionItem`, increments server `attempt_count`, and
  moves that item to the queue tail.
- Multiple attempts still produce one final `LearningEvent`.
- `occurred_at` outside server UTC time plus or minus 24 hours is rejected.
- The server deduplicates `attempt_id` values per item and derives the
  authoritative attempt count. `client_attempt_count` is audit-only.
- `client_event_id` and final `session_item_id` are unique.
- A batch is atomic. Mixed new and conflicting entries reject the whole batch.

Client conflict handling:

- `OUTCOME_ALREADY_RECORDED`: discard that local outcome and reload
  `GET /api/v1/study-sessions/{id}` for authoritative state.
- `IDEMPOTENCY_CONFLICT`: keep the local batch and retry with exponential
  backoff at most three times. If it persists, stop automatic playback and
  show a recoverable synchronization error.

## Statistics definitions

- `today_learned`: distinct term keys within event-local activity dates.
  Term keys are vocabulary-scoped, so identical terms in different
  vocabularies count separately.
- `due_reviews`: active, non-deleted entries with `next_review_at <= now`.
- `streak`: consecutive event-local activity dates. If today has no event,
  calculation starts from yesterday.
- Changing the current timezone affects only new events. Existing events retain
  the timezone and local activity date captured at write time.

## Error codes

`VALIDATION_ERROR`, `UNSUPPORTED_FILE_TYPE`, `MISSING_REQUIRED_COLUMNS`,
`EMPTY_VOCABULARY`, `RESOURCE_NOT_FOUND`, `CONFIRMATION_REQUIRED`,
`OUTCOME_ALREADY_RECORDED`, `IDEMPOTENCY_CONFLICT`, `UNAUTHORIZED`,
`CSRF_FAILED`, and `DATABASE_BUSY`.
