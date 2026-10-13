# ADR 005: Binary Leitner review state

Status: Accepted

WordStream records one final outcome per study-session item: `seen` or
`again`. A client may replay an item before deciding, but replay is not a third
learning result.

Review state uses five boxes with intervals of 1, 3, 7, 14, and 30 days:

- `seen` advances the item by one box, capped at box 4.
- `again` moves the item to box 0.
- `next_review_at` is the accepted event's `occurred_at` plus the interval for
  the resulting box.

The event write, session-item update, and review-state update occur in one
transaction. `client_event_id` makes request retries idempotent, while the
unique session-item event prevents two different final outcomes for one item.
An event timestamp more than 24 hours before or after server time is rejected.

Learning events are append-only historical facts. Review state is the current
projection and may be removed when its vocabulary is deleted.
