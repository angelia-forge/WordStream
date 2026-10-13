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
authoritative `current_index`. `current_index` is the completion frontier, not
the player's display cursor. Looking at a previous item never moves it back.

Settled outcomes use:

```text
POST /api/v1/study-sessions/{session_id}/outcomes/batch
```

Each outcome contains `session_item_id`, a client-generated UUID `attempt_id`,
`action=seen|again|replayed`, and timezone-aware `occurred_at`.

- A retry reuses the same `SessionItem`; it never creates a duplicate row.
- The retried item is inserted after up to two other items, so it becomes the
  third subsequent presentation when enough items remain, otherwise the tail.
- Every accepted presentation increments server-side `attempt_count`.
- The first `seen` or `again` locks the final result. A later `replayed`
  presentation cannot overwrite it.
- Multiple attempts still produce one final `LearningEvent`, keyed uniquely by
  `session_item_id`.
- `occurred_at` outside server UTC time plus or minus 24 hours is rejected with
  `VALIDATION_ERROR`.
- The server deduplicates `attempt_id` values per item and derives the
  authoritative attempt count.
- A batch is atomic. Mixed new and conflicting entries reject the whole batch.

The player keeps outcomes in memory and flushes after ten newly settled
results, on pause, page hiding, and before finishing. It uses an absolute
deadline for timing. Returning from a throttled background page advances at
most one item.

`POST /api/v1/study-sessions/{session_id}/finish` is idempotent. It writes one
history event and updates one review state for every item with a final result,
then marks the session finished. Unsettled items do not create history.

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

- `today_learned`: distinct vocabulary-scoped term keys within event-local
  activity dates.
- `due_reviews`: active, non-deleted entries with `next_review_at <= now`.
- `streak`: consecutive event-local activity dates. If today has no event,
  calculation starts from yesterday.
