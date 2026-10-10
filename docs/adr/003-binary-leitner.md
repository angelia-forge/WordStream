# ADR 003: Binary Leitner outcomes

Status: Accepted

Automatic read-along does not naturally collect four-level SM-2 ratings.
WordStream therefore records `seen` by default and lets the user select
`again`.

Retries reuse the same session item at the queue tail. Attempts accumulate,
but each session item creates one final learning event. Each presentation has
a unique attempt id; the server deduplicates those ids and derives the attempt
count. This aligns automatic playback, scheduling, idempotency, and
low-friction mobile interaction.
