# Stage 1 API Planning Baseline

This document records the Stage 1 vocabulary contract and preserves approved
planning decisions for later study stages. Vocabulary management and the
minimal history-retention schema are implemented; study-session endpoints
remain planning baselines.

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
- A study plan has `UNIQUE(vocabulary_id)` and is upserted with `PUT`.

## Study endpoints

`POST /api/v1/study-sessions` creates the queue and server-generated
`session_item_id` values. Clients only reference those identifiers.

Settled outcomes use:

```text
POST /api/v1/study-sessions/{session_id}/outcomes/batch
```

Each outcome contains `session_item_id`, `client_event_id`, `result`,
`attempts`, optional `client_attempt_count`, and `occurred_at`. Every attempt
contains a client-generated UUID `attempt_id` and its client timestamp.

- A retry reuses the same `SessionItem` and moves it to the queue tail.
- Every accepted presentation increments server-side `attempt_count`.
- Multiple attempts still produce one final `LearningEvent`.
- `occurred_at` outside server UTC time plus or minus 24 hours is rejected with
  `VALIDATION_ERROR`.
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
