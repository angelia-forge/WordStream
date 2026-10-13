# Learning Decisions

These product decisions describe the implemented learning behavior.

## Binary Leitner outcomes

Automatic read-along records `seen` by default and lets the learner select
`again`. The review intervals are 1, 3, 7, 14, and 30 days.

Boxes are numbered 0 through 4. A first outcome starts in box 0 and is due the
next day. `again` resets an existing state to box 0; `seen` advances an
existing state by one box, capped at box 4.

Retries reuse the same session item in the player queue, but only the first
final outcome creates a learning event. Its client-generated event id is the
idempotency key. Server attempt count is authoritative; the client count is
retained only for audit.

## Event-local activity dates

Each learning event stores timezone-aware client time, server creation time,
the active IANA timezone, and the derived local activity date.

Changing application timezone affects new events only. Historical daily
statistics and streaks are not retroactively regrouped.
