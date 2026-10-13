# Stage 1 API Planning Baseline

This document records the implemented vocabulary, study-plan, and read-along
session contracts.

## Vocabulary endpoints

- Each imported item becomes an `Entry` with `entry_type=word|phrase`, `term`,
  and `normalized_term`.
- Normalization is `lower(trim(collapse_whitespace(term)))`; the original term
  retains internal whitespace.
- Entry uniqueness is scoped by `UNIQUE(vocabulary_id, normalized_term)`.
- Preview uses `POST /api/v1/vocabularies/import/preview`; commit uses
  `POST /api/v1/vocabularies/import`. Both accept `multipart/form-data` with
  exactly one of `file` or `text`, plus `name` and `duplicate_policy=skip`.
- Preview returns a SHA-256 `preview_digest`. Commit reparses the source and
  rejects changed content or options with `409 PREVIEW_MISMATCH`.
- List endpoints use `page >= 1`, `1 <= page_size <= 100`, `q`, an enumerated
  `sort`, and `order=asc|desc`.
- Deletion uses
  `DELETE /api/v1/vocabularies/{id}?confirm_id={id}`. A missing or mismatched
  confirmation returns `409 CONFIRMATION_REQUIRED`. Entries, the vocabulary
  study plan, and entry review states cascade; learning events remain with
  `entry_id=NULL`.
- A study plan has `UNIQUE(vocabulary_id)` and is upserted with `PUT`. It stores
  `daily_new_count` and `daily_review_count` in the range 0 through 500,
  `interval_seconds` in the range 1 through 10, plus `is_random` and `is_loop`.

## Read-along queue

- Due reviews have a review state with non-null `next_review_at <= now`.
- New entries have no review state. An entry with a future or null
  `next_review_at` is neither due nor new.
- Without random mode, due reviews sort by due time then entry id; new entries
  sort by creation time then entry id.
- Random mode shuffles the two groups independently.
- Limits are applied after group ordering, then the queue is concatenated as
  reviews followed by new entries.
- `is_loop` is returned as player metadata and never changes server ordering.

## Study endpoints

`POST /api/v1/study-sessions` creates the queue and server-generated
`session_item_id` values. `resume_existing=true` returns the active session;
`false` abandons it before creating a new one. A missing plan returns
`PLAN_REQUIRED`; an empty queue returns `EMPTY_STUDY_QUEUE`.

`GET /api/v1/study-sessions/{session_id}` returns the persisted queue and
authoritative `current_index`. `current_index` is the number of finalized
items, not the player's display cursor. The player resumes at the first
unfinished item. Looking at a previous item never changes server progress.

Settled outcomes use:

```text
POST /api/v1/study-sessions/{session_id}/outcomes/batch
```

Each outcome contains `session_item_id`, a client-generated UUID
`client_event_id`, `result=seen|again`, client-observed `attempt_count`, and
timezone-aware `occurred_at`.

- The first `seen` or `again` locks the final result and immediately creates
  one `LearningEvent`, keyed uniquely by `session_item_id`.
- `again` resets an existing review state to box 0. A first outcome also starts
  at box 0. `seen` advances an existing state by one box, capped at box 4.
- Box intervals are 1, 3, 7, 14, and 30 days. Review timestamps are calculated
  from accepted `occurred_at`.
- The player may show an `again` item after up to two other items, but that
  replay is presentation-only and cannot create or overwrite an outcome.
- The server increments authoritative `attempt_count`; the submitted value is
  retained separately as `client_attempt_count` for audit.
- `occurred_at` outside server UTC time plus or minus 24 hours is rejected with
  `VALIDATION_ERROR`.
- Reusing `client_event_id` with identical content returns the original result.
  Reusing it with changed content returns `IDEMPOTENCY_CONFLICT`. A second id
  for the same session item returns `OUTCOME_ALREADY_RECORDED`.
- A batch is atomic. Mixed new and conflicting entries reject the whole batch.
- Concurrent uniqueness races have the same idempotency/conflict behavior.
  SQLite write lock exhaustion returns `503 DATABASE_BUSY`.

The player writes pending outcomes to a session-scoped `localStorage` outbox
before transmission and removes them only after acknowledgement. It flushes
after ten newly settled results, on pause, page hiding, before finishing, and
when connectivity returns. Network, 5xx, and `DATABASE_BUSY` failures use up
to three exponential-backoff attempts. It uses an absolute deadline for
timing. Returning from a throttled background page advances at most one item.

`POST /api/v1/study-sessions/{session_id}/finish` is idempotent and only marks
the session finished. Outcomes already wrote history and review state in their
batch transaction; unsettled items do not create history.

## Speech and player fallback

- The browser speaks the complete `term`; phrase whitespace is preserved.
- Missing Speech APIs, empty voices, delayed `voiceschanged`, and `speak()`
  failures never stop the timer.
- Empty voices wait briefly for `voiceschanged`, then switch to visible silent
  mode. A delayed voice event speaks the currently displayed term.
- Pause suspends speech and the remaining deadline. Previous only browses
  history; next resumes the authoritative frontier.

## Learning history

- `LearningEvent` is append-only.
- `entry_id` is nullable and uses `ON DELETE SET NULL`.
- Events retain `term_key`, `term_snapshot`, and a compact vocabulary snapshot
  containing only vocabulary id and name.
- Every event captures the active IANA timezone and derived local activity
  date when written. Later timezone changes do not rewrite history.

## Statistics definitions

- `today_learned`: distinct term keys whose stored event-local activity date
  equals today in the current application timezone.
- `due_reviews`: active, non-deleted entries with `next_review_at <= now`.
- `streak`: consecutive stored event-local activity dates. If today has no
  event, calculation starts from yesterday; two inactive days yield zero.
- `total_entries`: active, non-deleted entries.
- `vocabulary_id` filters history through the event vocabulary snapshot and
  live counts through current entries. Deleted vocabulary ids can still query
  retained history but have zero live counts.
- Outcome submission reads `AppSetting.timezone` inside the batch transaction
  and stores both that timezone and the derived activity date. A timezone
  update never rewrites historical events.

`GET /api/v1/statistics/today` returns today's learned count, streak, and total
entries. `GET /api/v1/reviews/today` returns the current due-review count. Both
accept an optional positive `vocabulary_id`.
